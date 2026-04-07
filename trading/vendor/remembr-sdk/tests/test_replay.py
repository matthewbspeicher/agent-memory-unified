from unittest.mock import MagicMock
from remembr.trading import TradingJournal


def test_replay_trades():
    client = MagicMock()
    client.post.return_value = {
        "data": {
            "total_trades": 5,
            "wins": 3,
            "losses": 2,
            "win_rate": 60.0,
            "total_pnl": 250.0,
            "trades": [],
        }
    }

    journal = TradingJournal(client, paper=False)
    result = journal.replay_trades(exit_offset_pct=-5.0)

    assert result["total_trades"] == 5
    assert result["total_pnl"] == 250.0
    client.post.assert_called_once_with(
        "/trading/replay",
        json={"paper": False, "exit_offset_pct": -5.0},
    )


def test_replay_with_overrides():
    client = MagicMock()
    client.post.return_value = {"data": {"total_trades": 1, "total_pnl": -100.0}}

    journal = TradingJournal(client, paper=False)
    result = journal.replay_trades(exit_overrides={"AAPL": "90.00"})

    assert result["total_pnl"] == -100.0
