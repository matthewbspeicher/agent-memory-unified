import asyncio
import logging

from config import Config
from journal.indexer import JournalIndexer

logger = logging.getLogger(__name__)


async def journal_persistence_loop(indexer: JournalIndexer, config: Config) -> None:
    """Background task to periodically persist the HNSW index to disk."""
    if not config.journal_index_enabled:
        return

    interval = config.journal_index_persist_interval
    if interval <= 0:
        logger.warning("Journal persistence task disabled: interval must be > 0.")
        return

    logger.info("Journal persistence loop started (interval: %ds)", interval)

    try:
        while True:
            await asyncio.sleep(interval)
            try:
                if indexer.is_ready:
                    await indexer.persist()
            except Exception as e:
                logger.error(
                    "Error during background journal persistence: %s",
                    str(e),
                    exc_info=True,
                )
    except asyncio.CancelledError:
        logger.info("Journal persistence loop cancelled.")
        raise
