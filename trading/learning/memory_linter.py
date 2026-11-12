import logging
from datetime import datetime, timezone
from learning.memory_client import TradingMemoryClient

logger = logging.getLogger(__name__)


class MemoryLinter:
    """Automated detection of conflicting rules and staleness across the knowledge base."""

    def __init__(self, memory_client: TradingMemoryClient):
        self._memory = memory_client

    async def lint(self) -> dict:
        """
        Checks the memory store for:
        - Staleness: flag memories past expires_at
        - Orphans: strategy articles with no supporting trade records
        """
        try:
            data = await self._memory._shared.search_commons(
                q="", limit=100, tags=["strategy_article"]
            )
            stale_count = 0
            orphan_count = 0
            invalid_expiry_count = 0
            unaccessed_count = 0
            now = datetime.now(timezone.utc)
            for mem in data:
                if mem.get("expires_at"):
                    try:
                        expiry = datetime.fromisoformat(
                            mem["expires_at"].replace("Z", "+00:00")
                        )
                        if expiry.tzinfo is None:
                            expiry = expiry.replace(tzinfo=timezone.utc)
                        stale_count += expiry <= now
                    except (TypeError, ValueError, AttributeError):
                        invalid_expiry_count += 1
                if mem.get("access_count", 1) == 0:
                    unaccessed_count += 1
                # Only explicit empty provenance establishes an orphan. Access
                # frequency is not evidence of whether an article has sources.
                metadata = mem.get("metadata") or {}
                sources = (
                    metadata.get("source_ids") if isinstance(metadata, dict) else None
                )
                if sources == []:
                    orphan_count += 1
            return {
                "ok": True,
                "stale_articles": stale_count,
                "orphan_articles": orphan_count,
                "total_strategies": len(data),
                "unaccessed_articles": unaccessed_count,
                "invalid_expiry_articles": invalid_expiry_count,
            }
        except Exception as e:
            logger.error("Memory linter failed: %s", e)
            return {"ok": False, "error": str(e)}
