"""Tests for MassiveDataSource adapter — specifically the free-tier
snapshot lockout behavior added 2026-04-17.

MassiveDataSource.get_quote hits the Massive snapshot endpoint, which
is paid-tier only. Free-tier accounts get 403 NOT_AUTHORIZED on every
request. Without a lockout, DataBus pays the roundtrip + log line on
every quote request before falling through to the next source. The
lockout flips on the first 403 and short-circuits subsequent calls so
the fallthrough is immediate.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from broker.models import Symbol, AssetType
from data.massive_source import MassiveDataSource


def _sym(t: str) -> Symbol:
    return Symbol(ticker=t, asset_type=AssetType.STOCK)


class TestSnapshotLockout:
    async def test_lockout_false_on_init(self):
        source = MassiveDataSource(client=MagicMock())
        assert source._snapshot_locked_out is False

    async def test_first_403_flips_lockout(self):
        client = MagicMock()
        client.get_snapshot = AsyncMock(
            side_effect=RuntimeError(
                "HTTP 403: NOT_AUTHORIZED — upgrade your plan at massive.com/pricing"
            )
        )
        source = MassiveDataSource(client=client)

        with pytest.raises(RuntimeError):
            await source.get_quote(_sym("AAPL"))

        assert source._snapshot_locked_out is True

    async def test_subsequent_calls_short_circuit_without_hitting_api(self):
        """Once locked out, get_quote raises immediately without calling
        the client — saves the roundtrip on every subsequent request."""
        client = MagicMock()
        client.get_snapshot = AsyncMock(
            side_effect=RuntimeError("HTTP 403: NOT_AUTHORIZED")
        )
        source = MassiveDataSource(client=client)

        # First call flips the lockout.
        with pytest.raises(RuntimeError):
            await source.get_quote(_sym("AAPL"))
        assert client.get_snapshot.call_count == 1

        # Second call must not hit the client.
        with pytest.raises(RuntimeError):
            await source.get_quote(_sym("MSFT"))
        assert client.get_snapshot.call_count == 1  # still 1, not 2

        # And a third for good measure.
        with pytest.raises(RuntimeError):
            await source.get_quote(_sym("GOOGL"))
        assert client.get_snapshot.call_count == 1

    async def test_lockout_triggers_on_not_entitled_phrase(self):
        """Massive's error body varies — the word 'NOT_AUTHORIZED' and the
        phrase 'not entitled to this data' both signal the free-tier
        lockout. Match loosely so minor response-shape drift doesn't
        break detection."""
        client = MagicMock()
        client.get_snapshot = AsyncMock(
            side_effect=RuntimeError(
                "You are not entitled to this data. Please upgrade your plan."
            )
        )
        source = MassiveDataSource(client=client)

        with pytest.raises(RuntimeError):
            await source.get_quote(_sym("AAPL"))
        assert source._snapshot_locked_out is True

    async def test_transient_500_does_not_flip_lockout(self):
        """A transient 5xx or network error must NOT flip the lockout —
        those are retriable conditions, not permanent plan limits."""
        client = MagicMock()
        client.get_snapshot = AsyncMock(
            side_effect=RuntimeError("HTTP 500: Internal Server Error")
        )
        source = MassiveDataSource(client=client)

        with pytest.raises(RuntimeError):
            await source.get_quote(_sym("AAPL"))
        assert source._snapshot_locked_out is False

    async def test_network_error_does_not_flip_lockout(self):
        client = MagicMock()
        client.get_snapshot = AsyncMock(
            side_effect=TimeoutError("Connection timed out")
        )
        source = MassiveDataSource(client=client)

        with pytest.raises(TimeoutError):
            await source.get_quote(_sym("AAPL"))
        assert source._snapshot_locked_out is False

    async def test_successful_call_leaves_lockout_off(self):
        client = MagicMock()
        client.get_snapshot = AsyncMock(
            return_value={
                "day": {"c": 200.0, "v": 1_000_000},
                "lastTrade": {"p": 200.5, "t": 1_700_000_000_000_000_000},
                "lastQuote": {"P": 200.6, "p": 200.4},
            }
        )
        source = MassiveDataSource(client=client)

        quote = await source.get_quote(_sym("AAPL"))
        assert quote.last is not None
        assert source._snapshot_locked_out is False
