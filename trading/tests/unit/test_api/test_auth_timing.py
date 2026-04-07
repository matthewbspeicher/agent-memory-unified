"""Tests for timing-safe API key verification."""

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from api.auth import verify_api_key


class TestApiKeyTiming:
    def test_verify_api_key_valid(self):
        """Valid key should pass."""
        mock_request = MagicMock()
        mock_request.app.state.config.api_key = "secret123"

        # Should not raise
        result = verify_api_key(mock_request, "secret123")
        assert result == "secret123"

    def test_verify_api_key_invalid(self):
        """Invalid key should raise 401."""
        mock_request = MagicMock()
        mock_request.app.state.config.api_key = "secret123"

        with pytest.raises(HTTPException) as exc:
            verify_api_key(mock_request, "wrong_key")
        assert exc.value.status_code == 401

    def test_verify_api_key_empty_config(self):
        """No API key configured should raise 503."""
        mock_request = MagicMock()
        mock_request.app.state.config.api_key = ""

        with pytest.raises(HTTPException) as exc:
            verify_api_key(mock_request, "any_key")
        assert exc.value.status_code == 503

    def test_timing_safe_comparison_used(self):
        """Verify hmac.compare_digest is used (can't test timing, but verify import)."""
        import hmac
        import inspect
        from api import auth

        # Check that hmac is imported in auth module
        assert hasattr(hmac, "compare_digest")
        source = inspect.getsource(auth)
        assert "hmac.compare_digest" in source
