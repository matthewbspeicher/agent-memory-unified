"""Tests for the GDELT DOC 2.0 headline fetcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from data.sources.gdelt import fetch_headlines


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
