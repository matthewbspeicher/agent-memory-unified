"""Tests for WeightSetter skip-reason instrumentation and audit-log
persistence (mirrors the evaluator pattern from a87e3d3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from integrations.bittensor.models import MinerRanking
from integrations.bittensor.weight_setter import (
    FAIL_CHAIN_ERROR,
    FAIL_CHAIN_RETURNED_FALSE,
    SKIP_INSUFFICIENT_RANKINGS,
    SKIP_NO_MATCHING_UIDS,
    SKIP_NO_METAGRAPH,
    SKIP_ZERO_SCORE,
    WeightSetter,
)
from storage.bittensor import BittensorStore


def _ranking(hotkey: str, score: float) -> MinerRanking:
    return MinerRanking(
        miner_hotkey=hotkey,
        windows_evaluated=10,
        direction_accuracy=0.6,
        mean_magnitude_error=0.1,
        mean_path_correlation=0.5,
        internal_score=score,
        latest_incentive_score=None,
        hybrid_score=score,
        alpha_used=1.0,
        updated_at=None,
    )


def _store(rankings: list[MinerRanking]) -> MagicMock:
    store = MagicMock(spec=BittensorStore)
    store.get_miner_rankings = AsyncMock(side_effect=lambda limit, symbol=None: rankings)
    store.save_weight_set_log = AsyncMock()
    return store



def _adapter(hotkeys: list[str] | None) -> MagicMock:
    adapter = MagicMock()
    if hotkeys is None:
        adapter.metagraph = None
    else:
        meta = MagicMock()
        meta.hotkeys = hotkeys
        adapter.metagraph = meta
    return adapter


def _setter(*, store, adapter, set_weights_return=True, set_weights_exc=None):
    subtensor = MagicMock()
    if set_weights_exc is not None:
        subtensor.set_weights = MagicMock(side_effect=set_weights_exc)
    else:
        subtensor.set_weights = MagicMock(return_value=set_weights_return)
    subtensor.block = 12345
    return WeightSetter(
        adapter=adapter,
        store=store,
        netuid=8,
        wallet=MagicMock(),
        subtensor=subtensor,
        set_interval=0.01,
        min_rankings=1,
    )


@pytest.mark.asyncio
async def test_insufficient_rankings_records_skip():
    store = _store([])
    setter = _setter(store=store, adapter=_adapter(["hk1"]))

    await setter._set_weights_once()

    assert setter.metrics.weight_sets_skipped == 1
    assert setter.metrics.last_weight_skip_reason == SKIP_INSUFFICIENT_RANKINGS
    assert setter.metrics.weight_sets_total == 0
    store.save_weight_set_log.assert_awaited_once()
    kwargs = store.save_weight_set_log.await_args.kwargs
    assert kwargs["status"] == "skipped"
    assert kwargs["skip_reason"] == SKIP_INSUFFICIENT_RANKINGS


@pytest.mark.asyncio
async def test_zero_score_records_skip():
    store = _store([_ranking("hk1", 0.0), _ranking("hk2", 0.0)])
    setter = _setter(store=store, adapter=_adapter(["hk1", "hk2"]))

    await setter._set_weights_once()

    assert setter.metrics.last_weight_skip_reason == SKIP_ZERO_SCORE
    assert setter.metrics.weight_sets_skipped == 1


@pytest.mark.asyncio
async def test_no_metagraph_records_skip():
    store = _store([_ranking("hk1", 0.5)])
    setter = _setter(store=store, adapter=_adapter(None))

    await setter._set_weights_once()

    assert setter.metrics.last_weight_skip_reason == SKIP_NO_METAGRAPH


@pytest.mark.asyncio
async def test_no_matching_uids_records_skip():
    # Ranking's hotkey is not in the metagraph
    store = _store([_ranking("hk_missing", 1.0)])
    setter = _setter(store=store, adapter=_adapter(["different_hotkey"]))

    await setter._set_weights_once()

    assert setter.metrics.last_weight_skip_reason == SKIP_NO_MATCHING_UIDS


@pytest.mark.asyncio
async def test_successful_set_records_success_log():
    store = _store([_ranking("hk1", 0.6), _ranking("hk2", 0.4)])
    setter = _setter(store=store, adapter=_adapter(["hk1", "hk2"]))

    await setter._set_weights_once()

    assert setter.metrics.weight_sets_total == 1
    assert setter.metrics.weight_sets_failed == 0
    assert setter.metrics.last_weight_set_block == 12345
    assert setter.metrics.last_weight_set_uid_count == 2
    assert setter.metrics.last_weight_set_at is not None

    store.save_weight_set_log.assert_awaited_once()
    kwargs = store.save_weight_set_log.await_args.kwargs
    assert kwargs["status"] == "success"
    assert kwargs["uid_count"] == 2
    assert kwargs["weights_payload"] is not None
    assert len(kwargs["weights_payload"]) == 2
    # Weights sum to ~1.0
    total = sum(w for _, w in kwargs["weights_payload"])
    assert abs(total - 1.0) < 1e-9


@pytest.mark.asyncio
async def test_chain_returns_false_records_failure():
    store = _store([_ranking("hk1", 1.0)])
    setter = _setter(
        store=store, adapter=_adapter(["hk1"]), set_weights_return=False
    )

    await setter._set_weights_once()

    assert setter.metrics.weight_sets_failed == 1
    assert setter.metrics.weight_sets_total == 0
    assert setter.metrics.last_weight_skip_reason == FAIL_CHAIN_RETURNED_FALSE
    kwargs = store.save_weight_set_log.await_args.kwargs
    assert kwargs["status"] == "failed"


@pytest.mark.asyncio
async def test_chain_exception_records_failure():
    store = _store([_ranking("hk1", 1.0)])
    setter = _setter(
        store=store,
        adapter=_adapter(["hk1"]),
        set_weights_exc=RuntimeError("chain timeout"),
    )

    await setter._set_weights_once()

    assert setter.metrics.weight_sets_failed == 1
    assert setter.metrics.last_weight_skip_reason == FAIL_CHAIN_ERROR
    kwargs = store.save_weight_set_log.await_args.kwargs
    assert kwargs["status"] == "failed"
    assert kwargs["skip_reason"] == FAIL_CHAIN_ERROR
    assert "chain timeout" in kwargs["error_detail"]


@pytest.mark.asyncio
async def test_audit_log_failure_is_non_fatal():
    """If save_weight_set_log raises, the setter should keep working."""
    store = _store([_ranking("hk1", 1.0)])
    store.save_weight_set_log = AsyncMock(side_effect=RuntimeError("db down"))
    setter = _setter(store=store, adapter=_adapter(["hk1"]))

    # Should not raise
    await setter._set_weights_once()

    # Metrics still update even though audit log failed
    assert setter.metrics.weight_sets_total == 1


@pytest.mark.asyncio
async def test_store_without_save_method_is_tolerated():
    """Older BittensorStore instances lacking save_weight_set_log must not crash."""
    store = MagicMock()
    store.get_miner_rankings = AsyncMock(return_value=[_ranking("hk1", 1.0)])
    # No save_weight_set_log attribute
    del_attrs = ["save_weight_set_log"]
    for a in del_attrs:
        if hasattr(store, a):
            delattr(store, a)
    store.save_weight_set_log = None  # explicit

    # getattr in _log_attempt returns None so the branch short-circuits
    setter = _setter(store=MagicMock(
        get_miner_rankings=AsyncMock(return_value=[_ranking("hk1", 1.0)]),
    ), adapter=_adapter(["hk1"]))
    # Remove the method entirely to trigger the "older store" branch
    if hasattr(setter._store, "save_weight_set_log"):
        delattr(setter._store, "save_weight_set_log")

    await setter._set_weights_once()
    assert setter.metrics.weight_sets_total == 1
