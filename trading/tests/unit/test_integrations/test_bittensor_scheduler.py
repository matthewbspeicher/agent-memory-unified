from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from integrations.bittensor.scheduler import TaoshiScheduler, next_hash_window


def test_next_hash_window_at_minute_0():
    now = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)
    result = next_hash_window(now)
    assert result.minute == 30
    assert result.second == 0


def test_next_hash_window_at_minute_15():
    now = datetime(2026, 3, 28, 12, 15, 0, tzinfo=timezone.utc)
    result = next_hash_window(now)
    assert result.minute == 30


def test_next_hash_window_at_minute_45():
    now = datetime(2026, 3, 28, 12, 45, 0, tzinfo=timezone.utc)
    result = next_hash_window(now)
    assert result.hour == 13
    assert result.minute == 0


def test_next_hash_window_at_minute_30():
    now = datetime(2026, 3, 28, 12, 30, 0, tzinfo=timezone.utc)
    result = next_hash_window(now)
    assert result.minute == 0
    assert result.hour == 13


def test_next_hash_window_inside_boundary_minute_advances():
    now = datetime(2026, 3, 28, 12, 0, 10, tzinfo=timezone.utc)
    result = next_hash_window(now)
    assert result.hour == 12
    assert result.minute == 30


async def test_select_miners_all_policy():
    mock_metagraph = MagicMock()
    mock_metagraph.uids = list(range(5))
    mock_metagraph.axons = [MagicMock() for _ in range(5)]
    mock_metagraph.I = [0.1, 0.5, 0.3, 0.8, 0.2]

    scheduler = TaoshiScheduler.__new__(TaoshiScheduler)
    scheduler._selection_policy = "all"
    scheduler._top_miners = 3
    scheduler._selection_metric = "incentive"

    selected = scheduler.select_miners(mock_metagraph)
    assert len(selected) == 5


async def test_select_miners_top_n_policy():
    mock_metagraph = MagicMock()
    mock_metagraph.uids = list(range(5))
    mock_metagraph.axons = [MagicMock() for _ in range(5)]
    mock_metagraph.I = [0.1, 0.5, 0.3, 0.8, 0.2]

    scheduler = TaoshiScheduler.__new__(TaoshiScheduler)
    scheduler._selection_policy = "top_n"
    scheduler._top_miners = 3
    scheduler._selection_metric = "incentive"

    selected = scheduler.select_miners(mock_metagraph)
    assert len(selected) == 3
    uids = [s[0] for s in selected]
    assert 3 in uids
    assert 1 in uids
