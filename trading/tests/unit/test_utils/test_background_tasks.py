# python/tests/unit/test_utils/test_background_tasks.py
import asyncio
import logging
import pytest
from utils.background_tasks import BackgroundTaskManager


class TestBackgroundTaskManager:
    async def test_register_and_cancel(self):
        mgr = BackgroundTaskManager()
        called = False

        async def worker():
            nonlocal called
            called = True
            await asyncio.sleep(999)

        mgr.create_task(worker(), name="test_worker")
        await asyncio.sleep(0.05)
        assert called
        assert "test_worker" in mgr.active_tasks

        await mgr.shutdown()
        assert len(mgr.active_tasks) == 0

    async def test_failed_task_logged(self, caplog):
        caplog.set_level(logging.ERROR)
        mgr = BackgroundTaskManager()

        async def bad_worker():
            raise ValueError("boom")

        task = mgr.create_task(bad_worker(), name="bad")
        try:
            await task
        except ValueError:
            pass
        # Wait a bit longer for log to propagate
        await asyncio.sleep(0.1)
        assert "boom" in caplog.text
        assert "bad" not in mgr.active_tasks

    async def test_shutdown_is_idempotent(self):
        mgr = BackgroundTaskManager()
        await mgr.shutdown()
        await mgr.shutdown()  # should not raise

    async def test_duplicate_name_raises(self):
        mgr = BackgroundTaskManager()

        async def worker():
            await asyncio.sleep(999)

        mgr.create_task(worker(), name="duplicate")
        coro = worker()
        with pytest.raises(
            ValueError, match="Task 'duplicate' is already registered and active"
        ):
            mgr.create_task(coro, name="duplicate")
        coro.close()
