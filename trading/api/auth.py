from functools import lru_cache

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from config import Config

_api_key_header = APIKeyHeader(name="X-API-Key")


@lru_cache(maxsize=1)
def _get_settings() -> Config:
    return Config()


def verify_api_key(
    api_key: str = Security(_api_key_header),
) -> str:
    settings = _get_settings()
    if not settings.api_key:
        raise HTTPException(status_code=503, detail="API not available — no API key configured")
    if api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key
