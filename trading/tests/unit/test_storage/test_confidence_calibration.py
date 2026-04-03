from __future__ import annotations

import aiosqlite
import pytest

from storage.db import init_db
from storage.confidence_calibration import ConfidenceCalibrationStore


@pytest.fixture
async def cal_store():
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await init_db(db)
    yield ConfidenceCalibrationStore(db)
    await db.close()


def _make_row(**overrides) -> dict:
    defaults = {
        "trade_count": 30,
        "win_rate": 0.60,
        "avg_net_pnl": "45.00",
        "avg_net_return_pct": 0.012,
        "expectancy": "0.012000",
        "profit_factor": 1.8,
        "max_drawdown": "-0.025",
        "calibrated_score": 0.0072,
        "sample_quality": "usable",
    }
    defaults.update(overrides)
    return defaults


class TestConfidenceCalibrationStore:
    async def test_upsert_and_get(self, cal_store: ConfidenceCalibrationStore):
        row = _make_row()
        await cal_store.upsert(
            agent_name="rsi_agent",
            confidence_bucket="0.70-0.80",
            window_label="all",
            **row,
        )

        result = await cal_store.get("rsi_agent", "0.70-0.80", "all")
        assert result is not None
        assert result["agent_name"] == "rsi_agent"
        assert result["confidence_bucket"] == "0.70-0.80"
        assert result["window_label"] == "all"
        assert result["trade_count"] == 30
        assert result["win_rate"] == pytest.approx(0.60)
        assert result["sample_quality"] == "usable"

    async def test_upsert_idempotency(self, cal_store: ConfidenceCalibrationStore):
        await cal_store.upsert(
            agent_name="rsi_agent",
            confidence_bucket="0.70-0.80",
            window_label="all",
            **_make_row(trade_count=30),
        )
        # Overwrite with updated trade count
        await cal_store.upsert(
            agent_name="rsi_agent",
            confidence_bucket="0.70-0.80",
            window_label="all",
            **_make_row(trade_count=45),
        )

        result = await cal_store.get("rsi_agent", "0.70-0.80", "all")
        assert result is not None
        assert result["trade_count"] == 45

        all_rows = await cal_store.list_all()
        assert len(all_rows) == 1

    async def test_composite_pk_distinct(self, cal_store: ConfidenceCalibrationStore):
        """Same agent+bucket, different windows → separate rows."""
        await cal_store.upsert(
            agent_name="rsi_agent",
            confidence_bucket="0.70-0.80",
            window_label="30d",
            **_make_row(trade_count=10),
        )
        await cal_store.upsert(
            agent_name="rsi_agent",
            confidence_bucket="0.70-0.80",
            window_label="90d",
            **_make_row(trade_count=25),
        )
        await cal_store.upsert(
            agent_name="rsi_agent",
            confidence_bucket="0.70-0.80",
            window_label="all",
            **_make_row(trade_count=40),
        )

        all_rows = await cal_store.list_all()
        assert len(all_rows) == 3

        r30 = await cal_store.get("rsi_agent", "0.70-0.80", "30d")
        r90 = await cal_store.get("rsi_agent", "0.70-0.80", "90d")
        rall = await cal_store.get("rsi_agent", "0.70-0.80", "all")
        assert r30["trade_count"] == 10
        assert r90["trade_count"] == 25
        assert rall["trade_count"] == 40

    async def test_list_by_strategy(self, cal_store: ConfidenceCalibrationStore):
        for bucket in ["0.60-0.70", "0.70-0.80", "0.80-0.90"]:
            await cal_store.upsert(
                agent_name="rsi_agent",
                confidence_bucket=bucket,
                window_label="all",
                **_make_row(),
            )
        # Different strategy
        await cal_store.upsert(
            agent_name="macd_agent",
            confidence_bucket="0.50-0.60",
            window_label="all",
            **_make_row(),
        )

        rsi_rows = await cal_store.list_by_strategy("rsi_agent")
        assert len(rsi_rows) == 3
        assert all(r["agent_name"] == "rsi_agent" for r in rsi_rows)

        macd_rows = await cal_store.list_by_strategy("macd_agent")
        assert len(macd_rows) == 1

    async def test_list_by_strategy_with_window_filter(self, cal_store: ConfidenceCalibrationStore):
        for wl in ["30d", "90d", "all"]:
            await cal_store.upsert(
                agent_name="rsi_agent",
                confidence_bucket="0.70-0.80",
                window_label=wl,
                **_make_row(),
            )

        rows_30d = await cal_store.list_by_strategy("rsi_agent", window_label="30d")
        assert len(rows_30d) == 1
        assert rows_30d[0]["window_label"] == "30d"

    async def test_list_all_with_window_filter(self, cal_store: ConfidenceCalibrationStore):
        await cal_store.upsert(
            agent_name="rsi_agent", confidence_bucket="0.70-0.80", window_label="30d", **_make_row()
        )
        await cal_store.upsert(
            agent_name="rsi_agent", confidence_bucket="0.70-0.80", window_label="all", **_make_row()
        )
        await cal_store.upsert(
            agent_name="macd_agent", confidence_bucket="0.50-0.60", window_label="all", **_make_row()
        )

        all_rows = await cal_store.list_all(window_label="all")
        assert len(all_rows) == 2
        assert all(r["window_label"] == "all" for r in all_rows)

    async def test_get_distinct_strategies(self, cal_store: ConfidenceCalibrationStore):
        for agent in ["rsi_agent", "macd_agent", "rsi_agent"]:
            await cal_store.upsert(
                agent_name=agent,
                confidence_bucket="0.70-0.80",
                window_label="all",
                **_make_row(),
            )

        strategies = await cal_store.get_distinct_strategies()
        assert strategies == ["macd_agent", "rsi_agent"]

    async def test_get_nonexistent(self, cal_store: ConfidenceCalibrationStore):
        result = await cal_store.get("nonexistent", "0.70-0.80", "all")
        assert result is None

    async def test_delete_by_strategy(self, cal_store: ConfidenceCalibrationStore):
        for bucket in ["0.60-0.70", "0.70-0.80"]:
            for wl in ["30d", "all"]:
                await cal_store.upsert(
                    agent_name="rsi_agent",
                    confidence_bucket=bucket,
                    window_label=wl,
                    **_make_row(),
                )

        all_rows = await cal_store.list_all()
        assert len(all_rows) == 4

        await cal_store.delete_by_strategy("rsi_agent", window_label="30d")
        remaining = await cal_store.list_all()
        assert len(remaining) == 2
        assert all(r["window_label"] == "all" for r in remaining)

    async def test_delete_all_windows(self, cal_store: ConfidenceCalibrationStore):
        for wl in ["30d", "90d", "all"]:
            await cal_store.upsert(
                agent_name="rsi_agent",
                confidence_bucket="0.70-0.80",
                window_label=wl,
                **_make_row(),
            )

        await cal_store.delete_by_strategy("rsi_agent")
        all_rows = await cal_store.list_all()
        assert len(all_rows) == 0

    async def test_unknown_bucket_stored(self, cal_store: ConfidenceCalibrationStore):
        """Null/unknown confidence bucket can be stored without error."""
        await cal_store.upsert(
            agent_name="rsi_agent",
            confidence_bucket="unknown",
            window_label="all",
            **_make_row(trade_count=5, sample_quality="insufficient"),
        )
        result = await cal_store.get("rsi_agent", "unknown", "all")
        assert result is not None
        assert result["confidence_bucket"] == "unknown"
