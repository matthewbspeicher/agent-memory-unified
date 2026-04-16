"""Tests for the GDELT DOC 2.0 headline fetcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

import data.sources.gdelt as gdelt_mod
from data.sources.gdelt import fetch_headlines


@pytest.fixture(autouse=True)
def _reset_throttle():
    """Reset GDELT throttle state between tests so we don't accidentally
    sleep during tests when one test landed close to the 5s window."""
    gdelt_mod._last_call_at = 0.0
    yield
    gdelt_mod._last_call_at = 0.0


@pytest.mark.asyncio
async def test_returns_titles_on_success() -> None:
    payload = {
        "articles": [
            {"title": "Fed holds rates steady", "url": "https://example.com/1"},
            {"title": "Inflation cools in June", "url": "https://example.com/2"},
            {"title": "", "url": "https://example.com/empty"},
            {"title": None, "url": "https://example.com/null"},
        ]
    }

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args, **kwargs) -> None:
            return None

        async def get(self, *args, **kwargs) -> _Resp:
            return _Resp()

    with patch("data.sources.gdelt.httpx.AsyncClient", return_value=_Client()):
        titles = await fetch_headlines("federal reserve")

    assert titles == ["Fed holds rates steady", "Inflation cools in June"]


@pytest.mark.asyncio
async def test_caps_at_max_records() -> None:
    payload = {"articles": [{"title": f"Story {i}"} for i in range(30)]}

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return payload

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args, **kwargs) -> None:
            return None

        async def get(self, *args, **kwargs) -> _Resp:
            return _Resp()

    with patch("data.sources.gdelt.httpx.AsyncClient", return_value=_Client()):
        titles = await fetch_headlines("test", max_records=5)

    assert len(titles) == 5
    assert titles == [f"Story {i}" for i in range(5)]


@pytest.mark.asyncio
async def test_returns_empty_on_network_error() -> None:
    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args, **kwargs) -> None:
            return None

        async def get(self, *args, **kwargs):
            raise httpx.ConnectError("down")

    with patch("data.sources.gdelt.httpx.AsyncClient", return_value=_Client()):
        titles = await fetch_headlines("anything")

    assert titles == []


@pytest.mark.asyncio
async def test_returns_empty_on_missing_articles_field() -> None:
    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"count": 0}  # no "articles" key at all

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args, **kwargs) -> None:
            return None

        async def get(self, *args, **kwargs) -> _Resp:
            return _Resp()

    with patch("data.sources.gdelt.httpx.AsyncClient", return_value=_Client()):
        titles = await fetch_headlines("q")

    assert titles == []


@pytest.mark.asyncio
async def test_returns_empty_on_429_rate_limit() -> None:
    """GDELT enforces one request per 5s per IP. HTTP 429 returns a
    plaintext (not JSON) body — must not raise, must log visibly."""

    class _Resp:
        status_code = 429

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError(
                "rate limited", request=object(), response=object()
            )

        def json(self) -> dict:
            raise ValueError("not JSON — plaintext reminder")

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args, **kwargs) -> None:
            return None

        async def get(self, *args, **kwargs) -> _Resp:
            return _Resp()

    with patch("data.sources.gdelt.httpx.AsyncClient", return_value=_Client()):
        titles = await fetch_headlines("q")

    assert titles == []
    # Timestamp updated so the next caller throttles appropriately
    assert gdelt_mod._last_call_at > 0


@pytest.mark.asyncio
async def test_throttle_serializes_concurrent_callers(monkeypatch) -> None:
    """Two concurrent fetches must not both fire a bare request — the
    in-process throttle must serialize them."""
    import asyncio

    call_times: list[float] = []

    class _Resp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"articles": []}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args, **kwargs) -> None:
            return None

        async def get(self, *args, **kwargs) -> _Resp:
            import time as _t

            call_times.append(_t.monotonic())
            return _Resp()

    # Stub out the 5.2s min so the test doesn't take forever
    monkeypatch.setattr(gdelt_mod, "_MIN_INTERVAL_SECONDS", 0.1)

    with patch("data.sources.gdelt.httpx.AsyncClient", return_value=_Client()):
        await asyncio.gather(
            fetch_headlines("a"),
            fetch_headlines("b"),
            fetch_headlines("c"),
        )

    assert len(call_times) == 3
    # Adjacent calls must be at least MIN_INTERVAL apart
    gaps = [call_times[i + 1] - call_times[i] for i in range(len(call_times) - 1)]
    assert all(g >= 0.09 for g in gaps), f"gaps={gaps}"
