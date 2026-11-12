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
