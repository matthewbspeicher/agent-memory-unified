import pytest
from datetime import datetime, timezone
from intelligence.models import IntelReport
from intelligence.enrichment import enrich_confidence


def _make_report(
    source: str,
    score: float,
    confidence: float,
    veto: bool = False,
    veto_reason: str | None = None,
) -> IntelReport:
    return IntelReport(
        source=source,
        symbol="BTCUSD",
        timestamp=datetime.now(timezone.utc),
        score=score,
        confidence=confidence,
        veto=veto,
        veto_reason=veto_reason,
        details={},
    )


WEIGHTS = {"on_chain": 0.15, "sentiment": 0.10, "anomaly": 0.05}


def test_no_reports_returns_base():
    conf, enrichment = enrich_confidence(0.65, 0.5, [], WEIGHTS)
    assert conf == 0.65
    assert enrichment.vetoed is False
    assert enrichment.adjustment == 0.0


def test_aligned_report_boosts_confidence():
    reports = [_make_report("on_chain", score=0.6, confidence=0.8)]
    conf, enrichment = enrich_confidence(0.65, 0.5, reports, WEIGHTS)
    assert conf > 0.65
    assert enrichment.adjustment > 0.0
    assert len(enrichment.contributions) == 1
    assert enrichment.contributions[0]["source"] == "on_chain"


def test_conflicting_report_is_ignored():
    reports = [_make_report("sentiment", score=-0.5, confidence=0.9)]
    conf, enrichment = enrich_confidence(0.65, 0.5, reports, WEIGHTS)
    assert conf == 0.65
    assert enrichment.adjustment == 0.0
    assert len(enrichment.contributions) == 0


def test_veto_returns_zero_confidence():
    reports = [
        _make_report(
            "anomaly",
            score=-0.8,
            confidence=0.9,
            veto=True,
            veto_reason="5x volume spike",
        )
    ]
    conf, enrichment = enrich_confidence(0.65, 0.5, reports, WEIGHTS)
    assert conf == 0.0
    assert enrichment.vetoed is True
    assert enrichment.veto_reason == "5x volume spike"


def test_adjustment_capped_at_30_percent():
    reports = [
        _make_report("on_chain", score=1.0, confidence=1.0),
        _make_report("sentiment", score=1.0, confidence=1.0),
        _make_report("anomaly", score=1.0, confidence=1.0),
    ]
    conf, enrichment = enrich_confidence(0.50, 1.0, reports, WEIGHTS)
    max_allowed = 0.50 + (0.50 * 0.30)
    assert conf <= max_allowed + 0.001
    assert conf > 0.50


def test_enrichment_clamps_to_one():
    reports = [_make_report("on_chain", score=1.0, confidence=1.0)]
    conf, enrichment = enrich_confidence(0.95, 1.0, reports, WEIGHTS)
    assert conf <= 1.0


def test_short_direction_with_bearish_intel():
    reports = [_make_report("on_chain", score=-0.6, confidence=0.8)]
    conf, enrichment = enrich_confidence(0.60, -0.5, reports, WEIGHTS)
    assert conf > 0.60
    assert enrichment.adjustment > 0.0


def test_unknown_source_gets_zero_weight():
    reports = [_make_report("unknown_source", score=1.0, confidence=1.0)]
    conf, enrichment = enrich_confidence(0.65, 0.5, reports, WEIGHTS)
    assert conf == 0.65
    assert enrichment.adjustment == 0.0


def test_zero_base_confidence():
    reports = [_make_report("on_chain", score=0.5, confidence=0.8)]
    conf, enrichment = enrich_confidence(0.0, 0.5, reports, WEIGHTS)
    assert conf == 0.0


def test_veto_checked_before_enrichment():
    reports = [
        _make_report(
            "anomaly",
            score=-0.9,
            confidence=0.95,
            veto=True,
            veto_reason="extreme volume",
        ),
        _make_report("on_chain", score=0.8, confidence=0.9),
    ]
    conf, enrichment = enrich_confidence(0.65, 0.5, reports, WEIGHTS)
    assert conf == 0.0
    assert enrichment.vetoed is True
