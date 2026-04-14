"""Tests for utils/health_cache — external service health cache."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_health_cache_updates_external_services():
    from utils.health_cache import HealthCacheManager

    cache = HealthCacheManager()

    with patch(
        "utils.health_cache.fetch_railway_status", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = {"status": "healthy", "deploy_status": "active"}

        await cache.update_external_health()

        status = cache.get_status("railway")
        assert status is not None
        assert status["status"] == "healthy"
        assert status["deploy_status"] == "active"


@pytest.mark.asyncio
async def test_health_cache_handles_fetch_error():
    from utils.health_cache import HealthCacheManager

    cache = HealthCacheManager()

    with patch(
        "utils.health_cache.fetch_railway_status", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.side_effect = RuntimeError("API down")

        await cache.update_external_health()

        status = cache.get_status("railway")
        assert status is not None
        assert status["status"] == "unhealthy"
        assert "API down" in status["message"]


def test_health_cache_returns_none_for_unknown_service():
    from utils.health_cache import HealthCacheManager

    cache = HealthCacheManager()
    assert cache.get_status("nonexistent") is None


@pytest.mark.asyncio
async def test_fetch_railway_status_returns_dict():
    """The default fetcher returns a valid shape even without a real API."""
    from utils.health_cache import fetch_railway_status

    result = await fetch_railway_status()
    assert isinstance(result, dict)
    assert "status" in result
