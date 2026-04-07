from functools import lru_cache

from fastapi import HTTPException, Security, Request
from fastapi.security import APIKeyHeader

from config import Config, load_config

_api_key_header = APIKeyHeader(name="X-API-Key")


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
    if api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key
