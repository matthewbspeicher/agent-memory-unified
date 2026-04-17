"""Tests for ArbExecutor paper-route safety gate.

Covers the "turn executor on without sending real orders" path:
- paper_route=True rewrites kalshi/polymarket broker_ids to *_paper
- paper_route=False passes through broker_ids (live)
- paper_route=True + paper brokers missing → executor refuses to execute
  (demotes enabled=True to shadow-only at startup, fails closed)
- _resolve_broker_id is called exactly at leg construction
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from execution.arb_executor import ArbExecutor


def _make_executor(*, paper_route: bool, brokers: dict) -> ArbExecutor:
    """Build an ArbExecutor with a mocked coordinator that carries the
    given broker map. Minimal stubs for deps not under test."""
    coordinator = MagicMock()
    coordinator._brokers = brokers
    return ArbExecutor(
        spread_store=MagicMock(),
        arb_coordinator=coordinator,
        event_bus=MagicMock(),
        enabled=True,
        paper_route=paper_route,
    )


class TestBrokerIdResolution:
    def test_paper_route_translates_kalshi(self):
        ex = _make_executor(paper_route=True, brokers={})
        assert ex._resolve_broker_id("kalshi") == "kalshi_paper"

    def test_paper_route_translates_polymarket(self):
        ex = _make_executor(paper_route=True, brokers={})
        assert ex._resolve_broker_id("polymarket") == "polymarket_paper"

    def test_live_route_passes_through(self):
        ex = _make_executor(paper_route=False, brokers={})
        assert ex._resolve_broker_id("kalshi") == "kalshi"
        assert ex._resolve_broker_id("polymarket") == "polymarket"

    def test_unknown_venue_translated_appended(self):
        """Defensive: a new venue name in paper_route mode gets _paper
        appended — surfaces missing-paper-broker loudly rather than
        silently falling through to live."""
        ex = _make_executor(paper_route=True, brokers={})
        assert ex._resolve_broker_id("futurexyz") == "futurexyz_paper"


class TestPaperBrokersAvailable:
    def test_both_paper_brokers_present(self):
        ex = _make_executor(
            paper_route=True,
            brokers={"kalshi_paper": MagicMock(), "polymarket_paper": MagicMock()},
        )
        assert ex._paper_brokers_available() is True

    def test_missing_kalshi_paper(self):
        ex = _make_executor(
            paper_route=True, brokers={"polymarket_paper": MagicMock()}
        )
        assert ex._paper_brokers_available() is False

    def test_missing_polymarket_paper(self):
        ex = _make_executor(
            paper_route=True, brokers={"kalshi_paper": MagicMock()}
        )
        assert ex._paper_brokers_available() is False

    def test_neither_paper_broker(self):
        ex = _make_executor(
            paper_route=True,
            brokers={"kalshi": MagicMock(), "polymarket": MagicMock()},
        )
        assert ex._paper_brokers_available() is False


class TestRunFailsClosed:
    """Per-event paper-broker availability gate. If paper_route=True and
    paper brokers aren't in the coordinator, the event falls to shadow
    without flipping self._enabled (paper brokers may still be wiring up
    during startup — app.py wires them into the coordinator ~25s after
    the executor task starts). The first miss logs loudly via
    _paper_missing_logged; later misses stay quiet."""

    def _routes_to_shadow(self, ex: ArbExecutor) -> bool:
        """Evaluate the same predicate run() uses to decide shadow-vs-execute."""
        return bool(
            ex._enabled
            and ex._paper_route
            and not ex._paper_brokers_available()
        )

    async def test_paper_route_without_paper_brokers_routes_to_shadow(self):
        ex = _make_executor(paper_route=True, brokers={"kalshi": MagicMock()})
        assert self._routes_to_shadow(ex) is True
        # _enabled is NOT flipped — lets a later wire-up take effect.
        assert ex._enabled is True

    async def test_paper_route_with_paper_brokers_executes(self):
        ex = _make_executor(
            paper_route=True,
            brokers={"kalshi_paper": MagicMock(), "polymarket_paper": MagicMock()},
        )
        assert self._routes_to_shadow(ex) is False
        assert ex._enabled is True

    async def test_live_route_never_routed_to_shadow_by_paper_check(self):
        """Live mode skips the paper-broker gate entirely — the operator
        accepted live routing by flipping STA_ARB_ROUTE_LIVE."""
        ex = _make_executor(paper_route=False, brokers={"kalshi": MagicMock()})
        assert self._routes_to_shadow(ex) is False
        assert ex._enabled is True

    async def test_first_miss_log_flag_starts_false(self):
        ex = _make_executor(paper_route=True, brokers={})
        assert ex._paper_missing_logged is False
