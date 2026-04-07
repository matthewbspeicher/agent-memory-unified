from unittest.mock import MagicMock
from remembr.trading import TradingJournal


def test_get_signals_returns_list():
    client = MagicMock()
    client.get_path.return_value = {
        "data": [
            {"trade_id": "t1", "ticker": "AAPL", "direction": "long"},
            {"trade_id": "t2", "ticker": "TSLA", "direction": "short"},
        ]
    }

    journal = TradingJournal(client, paper=False)
    signals = journal.get_signals()

    assert len(signals) == 2
    assert signals[0]["ticker"] == "AAPL"
    client.get_path.assert_called_once_with("/trading/signals", params={"limit": 50})


def test_get_signals_filters_by_ticker():
    client = MagicMock()
    client.get_path.return_value = {"data": [{"trade_id": "t1", "ticker": "AAPL"}]}

    journal = TradingJournal(client, paper=False)
    journal.get_signals(ticker="AAPL")

    client.get_path.assert_called_once_with(
        "/trading/signals", params={"limit": 50, "ticker": "AAPL"}
    )
