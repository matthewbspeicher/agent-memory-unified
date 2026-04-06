import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from config import Config
from journal.persistence_task import journal_persistence_loop


@pytest.mark.asyncio
async def test_persistence_task_lifecycle():
    indexer = MagicMock()
    indexer.is_ready = True
    indexer.persist = AsyncMock()

    settings = Config(journal_index_enabled=True, journal_index_persist_interval=300)

    call_count = 0

    async def mock_sleep(delay):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise asyncio.CancelledError()

    with patch("journal.persistence_task.asyncio.sleep", side_effect=mock_sleep):
        with pytest.raises(asyncio.CancelledError):
            await journal_persistence_loop(indexer, settings)

    indexer.persist.assert_awaited_once()


@pytest.mark.asyncio
async def test_persistence_task_disabled():
    indexer = MagicMock()
    indexer.persist = AsyncMock()

    # 0 interval disables the task
    settings = Config(journal_index_enabled=True, journal_index_persist_interval=0)

    await journal_persistence_loop(indexer, settings)

    indexer.persist.assert_not_called()
