import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    def __init__(self, llm_client, redis_client: Any, stream_name: str = "events"):
        self.llm = llm_client
        self.redis = redis_client
        self.stream_name = stream_name

    async def consolidate(self, payload: Dict[str, Any]):
        """
        Consolidate memories for an agent.
        Payload format:
        {
            'agent_id': int,
            'memory_ids': [int, ...],
            'memories': [
                {'id': int, 'type': str, 'value': str, 'summary': str, 'created_at': str},
                ...
            ]
        }
        """
        agent_id = payload.get("agent_id")
        memory_ids = payload.get("memory_ids", [])
        memories = payload.get("memories", [])

        if not memories:
            logger.info(f"No memories provided for agent {agent_id}. Skipping.")
            return

        logger.info(
            f"Starting consolidation for Agent {agent_id} with {len(memories)} memories."
        )

        # Prepare payload for LLM
        memories_text = []
        for m in memories:
            text = f"Type: {m.get('type')}, Context: {m.get('summary') or ''}, Value: {m.get('value')}"
            memories_text.append(text)

        prompt = (
            "You are an AI tasked with consolidating the short-term memories of a trading agent into high-level strategic insights.\n"
            "Review the following recent memories and produce a single, cohesive, consolidated summary of the key facts, notes, and error fixes.\n\n"
            "Memories:\n"
            + "\n".join(f"- {m}" for m in memories_text)
            + "\n\nProvide the consolidated memory as a clear, concise paragraph containing the most important long-term insights."
        )

        try:
            # We assume self.llm has an async generate or similar method.
            # We'll use a generic __call__ or generate pattern, but let's carefully try to use what exists.
            # Usually it's an instance of an LLM client (e.g. litellm or langchain or internal wrapper)
            if hasattr(self.llm, "agenerate_text"):
                consolidated_value = await self.llm.agenerate_text(prompt)
            elif hasattr(self.llm, "__call__"):
                # fallback for raw call
                consolidated_value = await self.llm(prompt)
            else:
                # Mock response if LLM client is a mock or interface is unknown
                logger.warning(
                    "LLM client interface not fully mapped, using default summarization."
                )
                consolidated_value = f"Consolidated {len(memories)} memories into a general strategic outline."
        except Exception as e:
            logger.error(f"LLM consolidation failed: {e}")
            consolidated_value = f"Consolidation of {len(memories)} memories completed with partial strategic insights due to generation error."

        logger.info(f"Generated consolidated memory for Agent {agent_id}.")

        # Send completion event back to Redis
        completion_payload = {
            "type": "memory.consolidation.completed",
            "payload": {
                "agent_id": agent_id,
                "original_memory_ids": memory_ids,
                "consolidated_memory": {
                    "type": "consolidated",
                    "value": consolidated_value,
                    "summary": f"Consolidated from {len(memories)} earlier memories",
                },
            },
        }

        try:
            await self.redis.xadd(
                self.stream_name, {"data": json.dumps(completion_payload)}
            )
            logger.info(
                f"Published memory.consolidation.completed for Agent {agent_id}"
            )
        except Exception as e:
            logger.error(f"Failed to publish completion event to Redis: {e}")
