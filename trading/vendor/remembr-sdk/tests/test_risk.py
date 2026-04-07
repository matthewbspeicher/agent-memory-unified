from unittest.mock import MagicMock
from remembr.trading import TradingJournal


def test_get_risk_metrics():
    client = MagicMock()
    client.get_path.return_value = {
        "data": [{"ticker": "AAPL", "unrealized_pnl": 100.0, "exposure": 1600.0}]
    }

    journal = TradingJournal(client, paper=False)
    result = journal.get_risk_metrics(market_prices={"AAPL": 160.0})

    assert len(result) == 1
    assert result[0]["unrealized_pnl"] == 100.0


def test_get_drawdown():
    client = MagicMock()
    client.get_path.return_value = {
        "data": {"max_drawdown": -50.0, "peak": 100.0, "trough": 50.0}
    }

    journal = TradingJournal(client, paper=False)
    result = journal.get_drawdown()

    assert result["max_drawdown"] == -50.0
