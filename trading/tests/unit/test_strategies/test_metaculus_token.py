"""Tests for Metaculus token wiring in kalshi_calibration and polymarket_calibration (Task 2)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.models import AgentConfig, ActionLevel


def _make_config(strategy: str, **params) -> AgentConfig:
    return AgentConfig(
        name=f"test_{strategy}",
        strategy=strategy,
        schedule="on_demand",
        action_level=ActionLevel.SUGGEST_TRADE,
        parameters=params,
    )


# ---------------------------------------------------------------------------
# KalshiCalibrationAgent — token fallback from settings
# ---------------------------------------------------------------------------

class TestKalshiCalibrationMetaculusToken:
    def _agent(self, **params):
        from strategies.kalshi_calibration import KalshiCalibrationAgent
        cfg = _make_config("kalshi_calibration", threshold_cents=5, min_volume=0, **params)
        return KalshiCalibrationAgent(cfg)

    @pytest.mark.asyncio
    async def test_token_from_params_passed_to_fetch(self):
        """Token provided in agent params is forwarded to _fetch_metaculus_questions."""
        agent = self._agent(metaculus_token="param-token")
        bus = MagicMock()
        bus._kalshi_source = AsyncMock()
        bus._kalshi_source.get_markets.return_value = []
        bus._settings = None

        with patch(
            "strategies.kalshi_calibration._fetch_metaculus_questions",
            new=AsyncMock(return_value=[]),
        ) as mock_fetch:
            await agent.scan(bus)

        mock_fetch.assert_awaited_once()
        _, kwargs = mock_fetch.call_args
        assert kwargs.get("token") == "param-token"

    @pytest.mark.asyncio
    async def test_token_falls_back_to_settings(self):
        """When no token in params, falls back to settings.metaculus_token."""
        agent = self._agent()  # no token in params
        bus = MagicMock()
        bus._kalshi_source = AsyncMock()
        bus._kalshi_source.get_markets.return_value = []
        settings = MagicMock()
        settings.metaculus_token = "settings-token"
        bus._settings = settings

        with patch(
            "strategies.kalshi_calibration._fetch_metaculus_questions",
            new=AsyncMock(return_value=[]),
        ) as mock_fetch:
            await agent.scan(bus)

        _, kwargs = mock_fetch.call_args
        assert kwargs.get("token") == "settings-token"

    @pytest.mark.asyncio
    async def test_no_token_passes_none(self):
        """With no token anywhere, None is passed (unauthenticated)."""
        agent = self._agent()
        bus = MagicMock()
        bus._kalshi_source = AsyncMock()
        bus._kalshi_source.get_markets.return_value = []
        bus._settings = None

        with patch(
            "strategies.kalshi_calibration._fetch_metaculus_questions",
            new=AsyncMock(return_value=[]),
        ) as mock_fetch:
            await agent.scan(bus)

        _, kwargs = mock_fetch.call_args
        assert kwargs.get("token") is None


# ---------------------------------------------------------------------------
# _fetch_metaculus_questions — Authorization header
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_metaculus_uses_token_header():
    """_fetch_metaculus_questions adds Authorization header when token is provided."""
    from strategies.kalshi_calibration import _fetch_metaculus_questions
    import httpx

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    captured_headers: list[dict] = []

    async def fake_get(url, params, headers):
        captured_headers.append(dict(headers))
        return mock_response

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = fake_get

    with patch("httpx.AsyncClient", return_value=mock_client):
        await _fetch_metaculus_questions(token="my-token")

    assert captured_headers, "No request was made"
    assert captured_headers[0].get("Authorization") == "Token my-token"


@pytest.mark.asyncio
async def test_fetch_metaculus_no_token_no_auth_header():
    """_fetch_metaculus_questions sends no Authorization header without a token."""
    from strategies.kalshi_calibration import _fetch_metaculus_questions

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    captured_headers: list[dict] = []

    async def fake_get(url, params, headers):
        captured_headers.append(dict(headers))
        return mock_response

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = fake_get

    with patch("httpx.AsyncClient", return_value=mock_client):
        await _fetch_metaculus_questions(token=None)

    assert "Authorization" not in captured_headers[0]


# ---------------------------------------------------------------------------
# PolymarketCalibrationAgent — token wiring
# ---------------------------------------------------------------------------

class TestPolymarketCalibrationMetaculusToken:
    def _agent(self, settings=None, **params):
        from strategies.polymarket_calibration import PolymarketCalibrationAgent
        cfg = _make_config("polymarket_calibration", **params)
        return PolymarketCalibrationAgent(cfg, settings=settings)

    def test_token_set_from_params(self):
        agent = self._agent(metaculus_token="param-token")
        assert agent.metaculus_token == "param-token"

    def test_token_falls_back_to_settings(self):
        settings = MagicMock()
        settings.metaculus_token = "settings-token"
        agent = self._agent(settings=settings)
        assert agent.metaculus_token == "settings-token"

    def test_token_none_when_not_configured(self):
        agent = self._agent()
        assert agent.metaculus_token is None

    def test_params_token_takes_priority_over_settings(self):
        settings = MagicMock()
        settings.metaculus_token = "settings-token"
        agent = self._agent(settings=settings, metaculus_token="param-token")
        assert agent.metaculus_token == "param-token"
