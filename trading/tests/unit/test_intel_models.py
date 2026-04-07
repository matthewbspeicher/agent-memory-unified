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
