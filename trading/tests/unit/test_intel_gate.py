from datetime import datetime, timedelta, timezone
from agents.models import AgentSignal


def test_enriched_signal_with_veto_payload():
    payload = {
        "symbol": "BTCUSD",
        "timeframe": "5m",
        "direction": "bullish",
        "confidence": 0.0,
        "expected_return": 0.003,
        "window_id": "20260407-1200",
        "miner_count": 5,
        "enriched_confidence": 0.0,
        "vetoed": True,
        "intel": {"veto_reason": "massive dump detected"},
    }
    signal = AgentSignal(
        source_agent="intelligence_layer",
        signal_type="intel_enriched_consensus",
        payload=payload,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    assert signal.payload["vetoed"] is True
    assert signal.payload["enriched_confidence"] == 0.0


def test_enriched_signal_with_boost():
    payload = {
        "symbol": "BTCUSD",
        "enriched_confidence": 0.78,
        "vetoed": False,
        "intel": {"base_confidence": 0.65, "adjustment": 0.13},
    }
    signal = AgentSignal(
        source_agent="intelligence_layer",
        signal_type="intel_enriched_consensus",
        payload=payload,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
    )
    assert signal.payload["vetoed"] is False
    assert signal.payload["enriched_confidence"] == 0.78
