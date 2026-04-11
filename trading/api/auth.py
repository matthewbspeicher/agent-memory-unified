from functools import lru_cache
import hashlib
import hmac
import logging

from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader

from config import Config, load_config

_api_key_header = APIKeyHeader(name="X-API-Key")
_agent_token_header = APIKeyHeader(name="X-Agent-Token", auto_error=False)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_settings() -> Config:
    return load_config()


def verify_api_key(
    request: Request,
    api_key: str = Security(_api_key_header),
) -> str:
    settings = getattr(request.app.state, "config", None) or _get_settings()
    if not settings.api_key:
        raise HTTPException(
            status_code=503, detail="API not available — no API key configured"
        )
    # Use timing-safe comparison to prevent timing attacks
    if not hmac.compare_digest(api_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


def verify_agent_token(
    request: Request,
    api_key: str = Depends(verify_api_key),
    agent_token: str | None = Security(_agent_token_header),
) -> str:
    """Verify agent identity via X-Agent-Token.
    
    If token is missing, falls back to 'anonymous_agent'.
    In a full implementation, tokens would be pre-registered hashes.
    """
    if not agent_token:
        return "anonymous_agent"
    
    # Basic verification: token should be hash of (agent_name + secret)
    # For now, we treat the token as the agent name for audit logging purposes,
    # as long as the master API key is valid.
    return agent_token
