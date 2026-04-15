"""
GDELT DOC 2.0 API client — free, no key, 15-minute-updated news graph.

Use as a fallback headline source when NewsAPI and RSS both yield
nothing. GDELT covers more languages, sources, and geographies than
NewsAPI and has no commercial-use restriction on the query output.

Endpoint: https://api.gdeltproject.org/api/v2/doc/doc
Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

The DOC API is a simple GET with query params. No auth. Rate limits
are generous but undocumented; we set a 10s timeout and fail soft.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"


async def fetch_headlines(
    query: str,
    *,
    max_records: int = 15,
    timespan: str = "1d",
    timeout: float = 10.0,
) -> list[str]:
    """Fetch recent article titles matching the query.

    Args:
        query: GDELT DOC search expression. Simple keyword strings work
            (e.g. "federal reserve rates"); the API supports boolean
            operators and language filters via the same string.
        max_records: cap on results returned. GDELT allows up to 250
            per call; default 15 matches the news-arb per-scan budget.
        timespan: GDELT timespan shorthand. "1d" = last 24h, "3d" = 72h,
            "1w" = 7 days. Shorter spans are cheaper and more relevant
            for fast-moving market questions.
        timeout: per-request timeout in seconds.

    Returns:
        List of article title strings. Empty list on any error
        (network, parse, rate limit) — caller is expected to treat
        empty as "no GDELT data" and fall back further.
    """
    params: dict[str, Any] = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": max_records,
        "timespan": timespan,
        "sort": "DateDesc",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(_ENDPOINT, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.debug("GDELT fetch failed for query '%s': %s", query, exc)
        return []

    articles = data.get("articles") or []
    titles: list[str] = []
    for art in articles:
        title = art.get("title")
        if title and isinstance(title, str):
            titles.append(title.strip())
    return titles[:max_records]
