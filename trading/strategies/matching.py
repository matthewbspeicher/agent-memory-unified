"""
EnhancedMatcher — three-step cross-platform market matching.

Steps:
1. Keyword Jaccard similarity with stop-word removal and light stemming.
2. Category alignment bonus (+0.10).
3. Close-date proximity penalty (0 to -0.30).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from broker.models import PredictionContract

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "in",
        "on",
        "will",
        "be",
        "by",
        "at",
        "of",
        "for",
        "is",
        "are",
        "was",
        "were",
        "to",
        "do",
        "that",
        "this",
        "it",
        "or",
    }
)

_CATEGORY_MAP: dict[str, str] = {
    "politics": "politics",
    "political": "politics",
    "economics": "economics",
    "economy": "economics",
    "economic": "economics",
    "finance": "economics",
    "financial": "economics",
    "climate": "climate",
    "environment": "climate",
    "weather": "climate",
    "sports": "sports",
    "sport": "sports",
    "crypto": "crypto",
    "cryptocurrency": "crypto",
    "blockchain": "crypto",
}


def extract_keywords(title: str) -> set[str]:
    """Return stemmed, stop-word-filtered tokens from title."""
    tokens = re.split(r"\W+", title.lower())
    result: set[str] = set()
    for t in tokens:
        if len(t) < 2 or t in _STOP_WORDS:
            continue
        # Poor-man's stemming: strip trailing 'ed' then 's'
        if t.endswith("ed") and len(t) > 4:
            t = t[:-2]
        elif t.endswith("s") and len(t) > 3:
            t = t[:-1]
        result.add(t)
    return result


def normalize_category(raw: str) -> str:
    """Map a raw category or tag string to one of the canonical categories."""
    key = raw.lower().strip()
    return _CATEGORY_MAP.get(key, "other")


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _date_penalty(
    k_close: datetime | str | None, p_close: datetime | str | None
) -> float:
    """Return 0.0, 0.10, 0.20, or 0.30 depending on how far apart the close dates are."""
    if not k_close or not p_close:
        return 0.0
    try:
        if isinstance(k_close, str):
            k_close = datetime.fromisoformat(k_close.replace("Z", "+00:00"))
        if isinstance(p_close, str):
            p_close = datetime.fromisoformat(p_close.replace("Z", "+00:00"))
        diff_days = abs((k_close - p_close).total_seconds() / 86400)
    except Exception:
        return 0.0
    if diff_days <= 7:
        return 0.0
    if diff_days <= 30:
        return 0.10
    if diff_days <= 90:
        return 0.20
    return 0.30


@dataclass(frozen=True)
class MatchCandidate:
    kalshi_ticker: str
    poly_ticker: str
    title_score: float  # Jaccard on stemmed keywords (0-1)
    category_bonus: float  # 0.10 if categories agree, else 0.0
    date_penalty: float  # 0.0 to 0.30
    final_score: float  # title_score + category_bonus - date_penalty


def match_markets(
    kalshi: list[PredictionContract],
    poly: list[PredictionContract],
    min_score: float = 0.35,
) -> list[MatchCandidate]:
    """
    Match kalshi markets to polymarket markets.

    Returns a list of MatchCandidate sorted descending by final_score.
    Each Kalshi and each Polymarket ticker appears at most once (greedy bipartite assignment).
    """
    # Pre-compute keyword sets
    k_keywords = {m.ticker: extract_keywords(m.title) for m in kalshi}
    p_keywords = {m.ticker: extract_keywords(m.title) for m in poly}

    # Collect all (k,p) candidates above threshold
    all_candidates: list[MatchCandidate] = []
    for k_mkt in kalshi:
        k_kw = k_keywords[k_mkt.ticker]
        k_cat = normalize_category(k_mkt.category)
        for p_mkt in poly:
            p_kw = p_keywords[p_mkt.ticker]
            title_score = _jaccard(k_kw, p_kw)
            p_cat = normalize_category(p_mkt.category)
            category_bonus = 0.10 if k_cat == p_cat and k_cat != "other" else 0.0
            date_penalty = _date_penalty(k_mkt.close_time, p_mkt.close_time)
            final_score = title_score + category_bonus - date_penalty
            if final_score >= min_score:
                all_candidates.append(
                    MatchCandidate(
                        kalshi_ticker=k_mkt.ticker,
                        poly_ticker=p_mkt.ticker,
                        title_score=title_score,
                        category_bonus=category_bonus,
                        date_penalty=date_penalty,
                        final_score=final_score,
                    )
                )

    # Greedy bipartite assignment: sort descending, claim each side once
    all_candidates.sort(key=lambda c: c.final_score, reverse=True)
    used_kalshi: set[str] = set()
    used_poly: set[str] = set()
    results: list[MatchCandidate] = []
    for cand in all_candidates:
        if cand.kalshi_ticker not in used_kalshi and cand.poly_ticker not in used_poly:
            results.append(cand)
            used_kalshi.add(cand.kalshi_ticker)
            used_poly.add(cand.poly_ticker)
    return results
