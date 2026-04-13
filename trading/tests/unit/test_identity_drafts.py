import sys
import pytest
import json
from unittest.mock import AsyncMock, MagicMock

# Mock asyncpg for import, then restore so later tests aren't polluted
_orig_asyncpg = sys.modules.get("asyncpg")
_orig_asyncpg_exc = sys.modules.get("asyncpg.exceptions")
sys.modules["asyncpg"] = MagicMock()
sys.modules["asyncpg.exceptions"] = MagicMock()

from api.identity.store import IdentityStore  # noqa: E402

# Restore originals (None means delete the mock entry)
if _orig_asyncpg is not None:
    sys.modules["asyncpg"] = _orig_asyncpg
else:
    sys.modules.pop("asyncpg", None)
if _orig_asyncpg_exc is not None:
    sys.modules["asyncpg.exceptions"] = _orig_asyncpg_exc
else:
    sys.modules.pop("asyncpg.exceptions", None)


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.fixture
def store(mock_pool):
    pool, _ = mock_pool
    return IdentityStore(pool)


@pytest.mark.asyncio
async def test_create_draft(store, mock_pool):
    pool, conn = mock_pool
    conn.fetchval = AsyncMock(return_value="test-uuid-123")

    draft_id = await store.create_draft(
        name="TestDraft",
        system_prompt="You are a test agent.",
        model="gpt-4o",
        hyperparameters={"temperature": 0.5},
    )

    assert draft_id == "test-uuid-123"
    conn.fetchval.assert_called_once()
    call_args = conn.fetchval.call_args
    assert call_args[0][1] == "TestDraft"
    assert call_args[0][2] == "You are a test agent."
    assert call_args[0][3] == "gpt-4o"
    assert json.loads(call_args[0][4]) == {"temperature": 0.5}


@pytest.mark.asyncio
async def test_create_draft_default_hyperparams(store, mock_pool):
    pool, conn = mock_pool
    conn.fetchval = AsyncMock(return_value="test-uuid-456")

    await store.create_draft(name="Test", system_prompt="Test prompt")

    call_args = conn.fetchval.call_args
    assert json.loads(call_args[0][4]) == {}


@pytest.mark.asyncio
async def test_get_draft(store, mock_pool):
    from datetime import datetime

    pool, conn = mock_pool
    now = datetime(2026, 4, 13, 12, 0, 0)
    conn.fetchrow = AsyncMock(
        return_value={
            "id": "test-uuid-123",
            "name": "TestDraft",
            "system_prompt": "Test prompt",
            "model": "gpt-4o",
            "hyperparameters": '{"temperature": 0.5}',
            "status": "draft",
            "backtest_results": None,
            "created_at": now,
            "updated_at": now,
        }
    )

    draft = await store.get_draft("test-uuid-123")

    assert draft is not None
    assert draft["id"] == "test-uuid-123"
    assert draft["name"] == "TestDraft"
    assert draft["status"] == "draft"
    assert draft["hyperparameters"]["temperature"] == 0.5
    assert draft["backtest_results"] is None


@pytest.mark.asyncio
async def test_get_draft_not_found(store, mock_pool):
    pool, conn = mock_pool
    conn.fetchrow = AsyncMock(return_value=None)

    draft = await store.get_draft("nonexistent")
    assert draft is None


@pytest.mark.asyncio
async def test_update_draft_results(store, mock_pool):
    pool, conn = mock_pool
    conn.execute = AsyncMock()

    results = {"sharpe_ratio": 1.5, "win_rate": 0.62, "equity_curve": []}
    await store.update_draft_results("test-uuid-123", results)

    conn.execute.assert_called_once()
    call_args = conn.execute.call_args
    assert call_args[0][1] == "test-uuid-123"
    assert json.loads(call_args[0][2]) == results


@pytest.mark.asyncio
async def test_update_draft_status(store, mock_pool):
    pool, conn = mock_pool
    conn.execute = AsyncMock()

    await store.update_draft_status("test-uuid-123", "deployed")

    conn.execute.assert_called_once()
    call_args = conn.execute.call_args
    assert call_args[0][1] == "test-uuid-123"
    assert call_args[0][2] == "deployed"


@pytest.mark.asyncio
async def test_list_drafts_no_filter(store, mock_pool):
    from datetime import datetime

    pool, conn = mock_pool
    now1 = datetime(2026, 4, 13, 12, 0, 0)
    now2 = datetime(2026, 4, 12, 10, 0, 0)
    conn.fetch = AsyncMock(
        return_value=[
            {
                "id": "uuid-1",
                "name": "Draft1",
                "system_prompt": "Prompt 1",
                "model": "gpt-4o",
                "hyperparameters": "{}",
                "status": "draft",
                "backtest_results": None,
                "created_at": now1,
                "updated_at": now1,
            },
            {
                "id": "uuid-2",
                "name": "Draft2",
                "system_prompt": "Prompt 2",
                "model": "claude-sonnet",
                "hyperparameters": "{}",
                "status": "tested",
                "backtest_results": '{"sharpe_ratio": 1.2}',
                "created_at": now2,
                "updated_at": now2,
            },
        ]
    )

    drafts = await store.list_drafts()
    assert len(drafts) == 2
    assert drafts[0]["name"] == "Draft1"
    assert drafts[1]["name"] == "Draft2"
    assert drafts[1]["backtest_results"]["sharpe_ratio"] == 1.2


@pytest.mark.asyncio
async def test_list_drafts_with_status_filter(store, mock_pool):
    pool, conn = mock_pool
    conn.fetch = AsyncMock(return_value=[])

    await store.list_drafts(status="tested")

    conn.fetch.assert_called_once()
    call_args = conn.fetch.call_args
    assert call_args[0][1] == "tested"


@pytest.mark.asyncio
async def test_delete_draft(store, mock_pool):
    pool, conn = mock_pool
    conn.execute = AsyncMock(return_value="DELETE 1")

    result = await store.delete_draft("test-uuid-123")
    assert result is True


@pytest.mark.asyncio
async def test_delete_draft_not_found(store, mock_pool):
    pool, conn = mock_pool
    conn.execute = AsyncMock(return_value="DELETE 0")

    result = await store.delete_draft("nonexistent")
    assert result is False


def test_row_to_draft_parses_json(store):
    from datetime import datetime

    now = datetime(2026, 4, 13, 12, 0, 0)
    row = {
        "id": "test-uuid",
        "name": "Test",
        "system_prompt": "Prompt",
        "model": "gpt-4o",
        "hyperparameters": '{"temperature": 0.7}',
        "status": "draft",
        "backtest_results": '{"sharpe_ratio": 1.0}',
        "created_at": now,
        "updated_at": now,
    }

    result = store._row_to_draft(row)

    assert result["id"] == "test-uuid"
    assert result["hyperparameters"] == {"temperature": 0.7}
    assert result["backtest_results"] == {"sharpe_ratio": 1.0}


def test_row_to_draft_handles_dict_passthrough(store):
    from datetime import datetime

    now = datetime(2026, 4, 13, 12, 0, 0)
    row = {
        "id": "test-uuid",
        "name": "Test",
        "system_prompt": "Prompt",
        "model": "gpt-4o",
        "hyperparameters": {"temperature": 0.7},
        "status": "draft",
        "backtest_results": {"sharpe_ratio": 1.0},
        "created_at": now,
        "updated_at": now,
    }

    result = store._row_to_draft(row)

    assert result["hyperparameters"] == {"temperature": 0.7}
    assert result["backtest_results"] == {"sharpe_ratio": 1.0}
