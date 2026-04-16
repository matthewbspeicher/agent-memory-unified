"""
GDELT DOC 2.0 API client — free, no key, 15-minute-updated news graph.

Use as a fallback headline source when NewsAPI and RSS both yield
nothing. GDELT covers more languages, sources, and geographies than
NewsAPI and has no commercial-use restriction on the query output.

Endpoint: https://api.gdeltproject.org/api/v2/doc/doc
Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/

The DOC API is a simple GET with query params. No auth. **GDELT
enforces a per-IP rate limit of one request every 5 seconds** —
violating it returns HTTP 429 with a plaintext reminder message
(not JSON). We throttle in-process to stay under the limit and log
429s visibly rather than swallowing them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT's documented per-IP limit. We add a small buffer to avoid
# clock-skew edge cases.
_MIN_INTERVAL_SECONDS = 5.2

# Module-level throttle state. The lock serializes the wait+timestamp
# update so concurrent scans don't each think they're clear to fire.
_throttle_lock = asyncio.Lock()
_last_call_at: float = 0.0


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
    global _last_call_at
    params: dict[str, Any] = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": max_records,
        "timespan": timespan,
        "sort": "DateDesc",
    }

    # Throttle to GDELT's documented 1-call-per-5s per-IP limit. Hold
    # the lock across the wait+request+timestamp update so concurrent
    # callers serialize cleanly.
    async with _throttle_lock:
        wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call_at)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(_ENDPOINT, params=params)
                if resp.status_code == 429:
                    logger.warning(
                        "GDELT rate-limited (HTTP 429) for query '%s' — in-process throttle at %.1fs may need adjustment",
                        query,
                        _MIN_INTERVAL_SECONDS,
                    )
                    _last_call_at = time.monotonic()
                    return []
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("GDELT fetch failed for query '%s': %s", query, exc)
            _last_call_at = time.monotonic()
            return []
        _last_call_at = time.monotonic()

    articles = data.get("articles") or []
    titles: list[str] = []
    for art in articles:
        title = art.get("title")
        if title and isinstance(title, str):
            titles.append(title.strip())
    return titles[:max_records]
