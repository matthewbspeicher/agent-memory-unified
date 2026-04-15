import time

from trading.utils.ids import new_signal_id


def test_new_signal_id_is_26_chars():
    sid = new_signal_id()
    assert len(sid) == 26


def test_new_signal_id_is_unique():
    ids = {new_signal_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_new_signal_ids_are_lexicographically_increasing():
    a = new_signal_id()
    time.sleep(0.001)
    b = new_signal_id()
    assert a < b
