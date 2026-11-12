"""Readers of stored dates and times must take text (SQLite) and datetimes (PostgreSQL)."""

from datetime import datetime, timedelta, timezone

import pytest

from journal.autopsy import _compute_duration
from learning.confidence_calibration import _exited_since
from storage.temporal import stored_datetime, stored_utc

UTC = timezone.utc
AWARE = datetime(2026, 11, 12, 12, 30, tzinfo=UTC)
NAIVE = AWARE.replace(tzinfo=None)  # what a TIMESTAMP column returns


def test_text_is_parsed_exactly_as_before():
    assert stored_datetime("2026-11-12T12:30:00+00:00") == AWARE
    assert stored_datetime("2026-11-12T12:30:00") == NAIVE
    assert stored_datetime("2026-11-12T12:30:00").tzinfo is None


def test_a_naive_datetime_from_postgresql_is_utc():
    assert stored_datetime(NAIVE) == AWARE
    assert stored_datetime(AWARE) is AWARE


@pytest.mark.parametrize(
    "value", [NAIVE, AWARE, "2026-11-12T12:30:00", "2026-11-12T21:30:00+09:00"]
)
def test_stored_utc_is_the_same_instant_however_it_was_stored(value):
    assert stored_utc(value) == AWARE
    assert stored_utc(value).tzinfo is not None


@pytest.mark.parametrize("bad", [None, "", "soon"])
def test_unreadable_values_raise_what_callers_already_catch(bad):
    with pytest.raises((TypeError, ValueError)):
        stored_utc(bad)


@pytest.mark.parametrize("exit_time", [NAIVE, AWARE, AWARE.isoformat(), NAIVE.isoformat()])
def test_calibration_window_filter_takes_either_form(exit_time):
    before = (AWARE - timedelta(days=1)).isoformat()
    after = (AWARE + timedelta(days=1)).isoformat()
    assert _exited_since(exit_time, before) is True
    assert _exited_since(exit_time, after) is False


def test_calibration_window_filter_excludes_a_missing_exit_time():
    assert _exited_since(None, AWARE.isoformat()) is False
    assert _exited_since("", AWARE.isoformat()) is False


@pytest.mark.parametrize("as_stored", [lambda d: d.isoformat(), lambda d: d.replace(tzinfo=None)])
def test_trade_duration_is_computed_from_either_form(as_stored):
    position = {
        "entry_time": as_stored(AWARE),
        "exit_time": as_stored(AWARE + timedelta(hours=3)),
    }
    assert _compute_duration(position) == "3.0 hours"


# --- Readers fixed after the audit ---


def test_positional_row_access_is_exact_when_columns_share_a_name():
    from storage.postgres import _Row

    class Record:
        """Like an asyncpg record: two output columns may have the same name."""

        def __init__(self, pairs):
            self._pairs = pairs

        def keys(self):
            return [k for k, _ in self._pairs]

        def values(self):
            return [v for _, v in self._pairs]

        def __getitem__(self, key):
            return dict(self._pairs)[key]

    row = _Row(Record([("sum", 1), ("sum", 2), ("n", 3)]))
    assert (row[0], row[1], row[2]) == (1, 2, 3)
    assert row["n"] == 3


@pytest.mark.parametrize("as_mapping", [True, False])
async def test_tax_export_reads_rows_from_either_backend(tmp_path, as_mapping):
    from storage.postgres import _Row
    from storage.trade_csv import TaxExporter

    columns = (
        "symbol entry_time exit_time entry_price exit_price entry_quantity"
        " entry_fees exit_fees net_pnl hold_minutes"
    ).split()
    values = ["AAPL", NAIVE, NAIVE + timedelta(days=2), "100", "110", "5", "1", "1", "48", 2880]
    if not as_mapping:  # SQLite returns text
        values[1], values[2] = values[1].isoformat(), values[2].isoformat()
    row = _Row(dict(zip(columns, values))) if as_mapping else tuple(values)

    class Cursor:
        async def fetchall(self):
            return [row]

    class Db:
        async def execute(self, sql, params):
            return Cursor()

    path = await TaxExporter(Db()).export_tax_report(2026, output_path=str(tmp_path / "t.csv"))
    lines = open(path).read().splitlines()
    assert lines[1] == "AAPL,2026-11-12,2026-11-14,550.00,501.00,49.00,S,,"


@pytest.mark.parametrize("bar_zone", [None, UTC])
async def test_evaluator_compares_bars_with_or_without_a_zone(bar_zone):
    from decimal import Decimal
    from unittest.mock import AsyncMock, MagicMock

    from broker.models import AssetType, Bar, Symbol
    from integrations.bittensor.evaluator import MinerEvaluator
    from integrations.bittensor.models import BittensorEvaluationWindow, BittensorMetrics

    symbol = Symbol("BTCUSD", AssetType.FOREX)
    bars = [
        Bar(symbol, close=Decimal("1"), open=Decimal("1"),
            timestamp=(AWARE + timedelta(minutes=5 * i)).replace(tzinfo=bar_zone))
        for i in range(-2, 1)
    ]
    data_bus = MagicMock()
    data_bus.get_historical = AsyncMock(return_value=bars)
    metrics = BittensorMetrics()
    evaluator = MinerEvaluator(store=MagicMock(), data_bus=data_bus, metrics=metrics)
    window = BittensorEvaluationWindow(
        window_id="w", symbol="BTCUSD", timeframe="5m", collected_at=AWARE, prediction_size=12
    )
    # One bar is at or after the window: the comparison ran, and found too few.
    await evaluator._evaluate_window(window)
    assert metrics.last_skip_reason == "insufficient_bars"


async def test_bitget_bar_times_are_instants():
    from unittest.mock import AsyncMock, MagicMock

    from adapters.bitget.adapter import BitGetMarketData
    from broker.models import AssetType, Symbol

    client = MagicMock()
    epoch_ms = int(AWARE.timestamp() * 1000)
    client.get_klines = AsyncMock(return_value=[[str(epoch_ms), "1", "2", "0.5", "1.5", "10"]])
    bars = await BitGetMarketData(client).get_historical(
        Symbol("BTCUSDT", AssetType.CRYPTO), "1h", "1d"
    )
    # Not the host's local wall time.
    assert bars[0].timestamp == AWARE and bars[0].timestamp.tzinfo is not None
