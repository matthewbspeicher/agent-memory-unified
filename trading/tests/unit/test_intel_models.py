import pytest
from datetime import datetime, timezone
from intelligence.models import IntelReport, IntelEnrichment, IntelRecord


def test_intel_report_creation():
    report = IntelReport(
        source="on_chain",
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        score=0.5,
        confidence=0.8,
        veto=False,
        veto_reason=None,
        details={"exchange_netflow": -1500.0},
    )
    assert report.source == "on_chain"
    assert report.score == 0.5
    assert report.veto is False


def test_intel_report_veto():
    report = IntelReport(
        source="anomaly",
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        score=-0.8,
        confidence=0.9,
        veto=True,
        veto_reason="Volume 5x normal against consensus",
        details={},
    )
    assert report.veto is True
    assert report.veto_reason == "Volume 5x normal against consensus"


def test_intel_enrichment_default():
    enrichment = IntelEnrichment(vetoed=False)
    assert enrichment.base_confidence == 0.0
    assert enrichment.adjustment == 0.0
    assert enrichment.final_confidence == 0.0
    assert enrichment.contributions == []


def test_intel_enrichment_vetoed():
    enrichment = IntelEnrichment(vetoed=True, veto_reason="dump signal")
    assert enrichment.vetoed is True
    assert enrichment.veto_reason == "dump signal"


def test_intel_record_creation():
    report = IntelReport(
        source="sentiment",
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        score=0.3,
        confidence=0.6,
        veto=False,
        veto_reason=None,
        details={},
    )
    record = IntelRecord(
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        provider="sentiment",
        report=report,
        latency_ms=95,
    )
    assert record.provider == "sentiment"
    assert record.latency_ms == 95


def test_intelligence_config_defaults():
    from intelligence.config import IntelligenceConfig

    cfg = IntelligenceConfig()
    assert cfg.enabled is False
    assert cfg.timeout_ms == 2000
    assert cfg.veto_threshold == 1
    assert cfg.weights == {
        "on_chain": 0.15,
        "sentiment": 0.10,
        "anomaly": 0.05,
        "order_flow": 0.12,
        "regime": 0.10,
        "risk_audit": 0.05,
    }
    assert cfg.max_adjustment_pct == 0.30


def test_intelligence_config_from_env(monkeypatch):
    monkeypatch.setenv("STA_INTEL_ENABLED", "true")
    monkeypatch.setenv("STA_INTEL_TIMEOUT_MS", "3000")
    monkeypatch.setenv("STA_INTEL_VETO_THRESHOLD", "2")
    monkeypatch.setenv("STA_INTEL_COINGLASS_API_KEY", "test-key-123")

    from config import load_config

    cfg = load_config(env_file="/dev/null")
    assert cfg.intel.enabled is True
    assert cfg.intel.timeout_ms == 3000
    assert cfg.intel.veto_threshold == 2
    assert cfg.intel.coinglass_api_key == "test-key-123"
