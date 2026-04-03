# strategies/llm_analyst.py
from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime

import anthropic

from agents.base import LLMAgent
from agents.models import Opportunity
from broker.models import Symbol
from data.bus import DataBus

try:
    from mcp import StdioServerParameters, ClientSession
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
import os

logger = logging.getLogger(__name__)


class LLMAnalystAgent(LLMAgent):
    @property
    def description(self) -> str:
        return f"AI analyst using {self.model}"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        symbols = data.get_universe(self.config.universe)

        # Gather market data summary
        market_summary = await self._build_market_summary(data, symbols[:20])

        try:
            client = anthropic.AsyncAnthropic()
            
            messages = [{"role": "user", "content": f"Analyze this market data and return opportunities:\n\n{market_summary}\n\nRespond with a JSON array of objects with fields: ticker, signal, confidence (0-1), reasoning"}]
            system_prompt = self.system_prompt or "You are a market analyst. Analyze the data and return trading opportunities as JSON."
            
            if hasattr(self.config, "remembr_api_token") and self.config.remembr_api_token:
                env = os.environ.copy()
                env["REMEMBR_API_KEY"] = self.config.remembr_api_token
                server_params = StdioServerParameters(
                    command="npx",
                    args=["-y", "@remembr/mcp-server"],
                    env=env
                )
                async with stdio_client(server_params) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        anthropic_tools = [
                            {
                                "name": t.name,
                                "description": t.description,
                                "input_schema": t.inputSchema
                            } for t in tools_result.tools
                        ]
                        
                        while True:
                            response = await client.messages.create(
                                model=self.model,
                                max_tokens=2048,
                                system=system_prompt,
                                messages=messages,
                                tools=anthropic_tools
                            )
                            
                            if response.stop_reason == "tool_use":
                                # Model wants to use tools
                                messages.append({"role": "assistant", "content": response.content})
                                tool_results = []
                                for block in response.content:
                                    if block.type == "tool_use":
                                        logger.info(f"Agent {self.name} calling MCP tool {block.name}")
                                        try:
                                            result = await session.call_tool(block.name, arguments=block.input)
                                            # format the MCP text/image contents back for anthropic
                                            formatted_content = []
                                            for c in result.content:
                                                if c.type == "text":
                                                    formatted_content.append({"type": "text", "text": c.text})
                                            
                                            tool_results.append({
                                                "type": "tool_result",
                                                "tool_use_id": block.id,
                                                "content": formatted_content,
                                                "is_error": result.isError
                                            })
                                        except Exception as e:
                                            logger.error(f"MCP tool {block.name} failed: {e}")
                                            tool_results.append({
                                                "type": "tool_result",
                                                "tool_use_id": block.id,
                                                "is_error": True,
                                                "content": [{"type": "text", "text": str(e)}]
                                            })
                                messages.append({"role": "user", "content": tool_results})
                            else:
                                break
            else:
                # Basic non-tool usage flow
                response = await client.messages.create(
                    model=self.model,
                    max_tokens=2048,
                    system=system_prompt,
                    messages=messages,
                )
            
            final_text = next((block.text for block in response.content if hasattr(block, "type") and block.type == "text"), "")
            return self._parse_response(final_text)
        except Exception as e:
            logger.error("LLM scan failed: %s", e)
            return []

    async def _build_market_summary(self, data: DataBus, symbols: list[Symbol]) -> str:
        lines = []
        for symbol in symbols:
            try:
                quote = await data.get_quote(symbol)
                rsi = await data.get_rsi(symbol, 14)
                lines.append(f"{symbol.ticker}: last={quote.last}, RSI(14)={rsi:.1f}, vol={quote.volume:,}")
            except Exception:
                continue
        return "\n".join(lines)

    def _parse_response(self, text: str) -> list[Opportunity]:
        try:
            # Try to extract JSON from the response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start == -1 or end == 0:
                logger.warning("No JSON array found in LLM response")
                return []
            items = json.loads(text[start:end])
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse LLM response as JSON: %s", e)
            return []

        opportunities = []
        for item in items:
            try:
                opportunities.append(Opportunity(
                    id=str(uuid.uuid4()),
                    agent_name=self.name,
                    symbol=Symbol(ticker=item["ticker"]),
                    signal=item.get("signal", "LLM_SIGNAL"),
                    confidence=float(item.get("confidence", 0.5)),
                    reasoning=item.get("reasoning", ""),
                    data=item,
                    timestamp=datetime.utcnow(),
                ))
            except (KeyError, ValueError) as e:
                logger.warning("Skipping invalid LLM opportunity: %s", e)
                continue
        return opportunities
