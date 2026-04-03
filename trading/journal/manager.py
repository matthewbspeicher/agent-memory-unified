import asyncio
import logging
from typing import TYPE_CHECKING, Optional
from decimal import Decimal

from journal.models import TradeLifecycle, TradeDecisionSnapshot, TradeExecutionLog

if TYPE_CHECKING:
    from data.events import EventBus
    from journal.indexer import JournalIndexer

logger = logging.getLogger(__name__)


class JournalManager:
    """
    Manages the semantic memory journaling of trades using the remembr-sdk.
    """

    def __init__(
        self,
        client,
        *,
        event_bus: "EventBus | None" = None,
        indexer: "JournalIndexer | None" = None,
        oracle_url: str | None = None,
    ):
        self._client = client
        self._event_bus = event_bus
        self._indexer = indexer
        self._oracle_url = oracle_url

    async def log_trade(self, lifecycle: TradeLifecycle) -> Optional[str]:
        """
        Logs a trade decision and execution to the journal.
        Returns the memory ID from Remembr.
        """
        try:
            content = (
                f"Trade {lifecycle.trade_id} [{lifecycle.decision.direction} {lifecycle.decision.symbol}]\n"
                f"Agent: {lifecycle.decision.agent_name}\n"
                f"Confidence: {lifecycle.decision.confidence}\n"
                f"Reasoning: {lifecycle.decision.reasoning}\n"
            )

            if lifecycle.execution:
                content += (
                    f"Execution: Filled {lifecycle.execution.filled_quantity} "
                    f"@ {lifecycle.execution.avg_fill_price}\n"
                )

            metadata = lifecycle.model_dump(mode="json")

            result = await self._client.store(
                value=content,
                visibility="private",
                tags=[
                    "trade_journal",
                    f"agent:{lifecycle.decision.agent_name}",
                    f"symbol:{lifecycle.decision.symbol}",
                    f"trade_id:{lifecycle.trade_id}",
                ],
                metadata=metadata,
            )
            memory_id = result.get("id")

            if memory_id and self._event_bus:
                await self._event_bus.publish("journal.entry_added", {
                    "memory_id": memory_id,
                    "trade_id": lifecycle.trade_id,
                    "content": content,
                    "metadata": metadata,
                })

            return memory_id

        except Exception as e:
            logger.error(f"Failed to log trade {lifecycle.trade_id} to journal: {e}")
            return None

    async def log_trade_entry(
        self,
        trade_id: str,
        decision: TradeDecisionSnapshot,
        execution: TradeExecutionLog,
        tags: list[str] | None = None,
    ) -> Optional[str]:
        """
        Convenience method for logging a trade from router/arb coordinator
        using the snapshot models. Converts to TradeLifecycle internally.
        """
        lifecycle = TradeLifecycle(
            trade_id=trade_id,
            decision=decision.to_trade_decision(),
            execution=execution.to_trade_execution(),
            status="open",
        )
        return await self.log_trade(lifecycle)

    async def update_trade_exit(
        self, trade_id: str, exit_execution, realized_pnl: Decimal, exit_reason: str
    ) -> bool:
        """
        Updates an existing journal entry with exit execution details.
        Uses store() with the same key to overwrite, since AsyncRemembrClient
        has no dedicated update method.
        """
        memory_id = None
        try:
            results = await self._client.search(
                q="",
                limit=1,
                tags=[f"trade_id:{trade_id}"],
            )

            if not results:
                logger.warning(f"Could not find journal entry for trade {trade_id}")
                return False

            memory_id = results[0].get("id")
            if not memory_id:
                return False

            # Fetch the existing memory, merge exit data, and re-store
            existing = await self._client.get(memory_id)
            metadata = existing.get("metadata", {})
            metadata["exit_execution"] = (
                exit_execution.model_dump(mode="json") if exit_execution else None
            )
            metadata["realized_pnl"] = (
                float(realized_pnl) if realized_pnl is not None else None
            )
            metadata["exit_reason"] = exit_reason
            metadata["status"] = "closed"

            value = existing.get("value", "")
            value += f"\nExit: {exit_reason} | PnL: {realized_pnl}"

            await self._client.store(
                value=value,
                key=memory_id,
                visibility="private",
                metadata=metadata,
                tags=existing.get("tags", []),
            )

            if self._event_bus:
                await self._event_bus.publish("journal.entry_updated", {
                    "memory_id": memory_id,
                    "trade_id": trade_id,
                    "content": value,
                    "metadata": metadata,
                })

            return True

        except Exception as e:
            logger.error(
                f"Failed to update trade exit for trade {trade_id} (memory_id={memory_id}): {e}"
            )
            return False

    async def get_recent_trades(self, symbol: str, limit: int = 20) -> list[dict]:
        """
        Retrieves recent journal entries for a specific symbol, ordered by timestamp.
        Uses the local indexer when available for fast lookups, falls back to remembr.
        """
        if self._indexer and self._indexer.is_ready:
            try:
                search_results = self._indexer.get_by_symbol(symbol, limit)
                return [
                    {"id": r.memory_id, "score": r.score, "content": r.content, "metadata": r.metadata}
                    for r in search_results
                ]
            except Exception as e:
                logger.warning(f"Indexer get_by_symbol failed for {symbol}, falling back to remembr: {e}")

        try:
            from datetime import datetime, timezone

            results = await self._client.search(
                q="",
                limit=limit,
                tags=["trade_journal", f"symbol:{symbol}"],
            )

            def get_timestamp(res):
                try:
                    ts_str = (
                        res.get("metadata", {}).get("decision", {}).get("timestamp", "")
                    )
                    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except Exception:
                    return datetime.min.replace(tzinfo=timezone.utc)

            results.sort(key=get_timestamp, reverse=True)
            return results
        except Exception as e:
            logger.error(f"Failed to fetch recent trades for {symbol}: {e}")
            return []

    async def query_similar_trades(self, query: str, limit: int = 5) -> list[dict]:
        """
        Queries the journal for trades similar to the current context.
        Uses the local indexer when available for semantic search,
        falls back to Oracle node if configured, then finally to Remembr.
        """
        # 1. Local Indexer (Fastest)
        if self._indexer and self._indexer.is_ready:
            try:
                search_results = await asyncio.to_thread(self._indexer.search, query, limit)
                return [
                    {"id": r.memory_id, "score": r.score, "content": r.content, "metadata": r.metadata}
                    for r in search_results
                ]
            except Exception as e:
                logger.warning(f"Local indexer search failed: {e}")

        # 2. Oracle Node (GPU accelerated, remote)
        if self._oracle_url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"{self._oracle_url}/journal/search",
                        params={"q": query, "limit": limit}
                    )
                    if resp.status_code == 200:
                        return resp.json()
                    else:
                        logger.warning(f"Oracle search failed with status {resp.status_code}")
            except Exception as e:
                logger.warning(f"Failed to call Oracle search API: {e}")

        # 3. Remembr API (Slowest, fallback)
        try:
            results = await self._client.search(
                q=query,
                limit=limit,
                tags=["trade_journal"],
            )
            return results
        except Exception as e:
            logger.error(f"Failed to query similar trades: {e}")
            return []
