from __future__ import annotations

from intelligence.models import IntelReport, IntelEnrichment


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _sign(x: float) -> float:
    if x > 0:
        return 1.0
    elif x < 0:
        return -1.0
    return 0.0


def enrich_confidence(
    base_confidence: float,
    direction_score: float,
    reports: list[IntelReport],
    weights: dict[str, float],
    max_adjustment_pct: float = 0.30,
) -> tuple[float, IntelEnrichment]:
    """Enrich a base confidence score using intel reports.

    Returns (enriched_confidence, enrichment_details).
    """
    base_confidence = _clamp(base_confidence, 0.0, 1.0)
    total_adjustment = 0.0
    contributions: list[dict] = []

    for report in reports:
        if report.veto:
            return 0.0, IntelEnrichment(
                vetoed=True, veto_reason=report.veto_reason
            )

        alignment = report.score * _sign(direction_score)

        # v1: only boost on positive alignment
        if alignment > 0:
            weight = weights.get(report.source, 0.0)
            adjustment = alignment * report.confidence * weight
            total_adjustment += adjustment
            contributions.append({
                "source": report.source,
                "adjustment": adjustment,
                "alignment": alignment,
            })

    max_adjustment = base_confidence * max_adjustment_pct
    total_adjustment = _clamp(total_adjustment, -max_adjustment, max_adjustment)
    enriched = _clamp(base_confidence + total_adjustment, 0.0, 1.0)

    return enriched, IntelEnrichment(
        vetoed=False,
        base_confidence=base_confidence,
        adjustment=total_adjustment,
        final_confidence=enriched,
        contributions=contributions,
    )
