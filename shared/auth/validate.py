# shared/auth/validate.py
from __future__ import annotations

import jwt
import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redis.asyncio import Redis


class TokenValidationError(Exception):
    """Token validation failed."""

    pass


async def validate_token(
    token: str, redis: Redis, db, jwt_secret: str = None, jwt_algorithm: str = "HS256"
) -> dict:
    """
    Hybrid token validator: JWT first, then legacy token hash.

    Args:
        token: Bearer token from Authorization header
        redis: Redis connection for blacklist checks
        db: Database connection for legacy token lookup
        jwt_secret: JWT signing secret (from env)
        jwt_algorithm: JWT algorithm (default HS256)

    Returns:
        dict with sub, type, scopes

    Raises:
        TokenValidationError: if token invalid or revoked
    """
    if jwt_secret and (len(jwt_secret) < 32 or "CHANGE_ME" in jwt_secret):
        raise TokenValidationError(
            "JWT_SECRET must be at least 32 characters long and not contain CHANGE_ME"
        )

    # Try JWT validation (new tokens)
    if not token.startswith("amc_"):
        try:
            # Decode JWT
            payload = jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])

            # Check Redis blacklist
            user_id = payload["sub"]

            # Check wildcard revocation
            is_wildcard_revoked = await redis.sismember(
                f"revoked_tokens:{user_id}", "*"
            )
            if is_wildcard_revoked:
                raise TokenValidationError("Token revoked (wildcard)")

            # Check specific token revocation
            is_token_revoked = await redis.sismember(f"revoked_tokens:{user_id}", token)
            if is_token_revoked:
                raise TokenValidationError("Token revoked (specific)")

            return payload  # Fast path, no DB hit

        except jwt.ExpiredSignatureError:
            raise TokenValidationError("Token expired")
        except jwt.InvalidTokenError as e:
            raise TokenValidationError(f"Invalid token: {e}")

    # Fallback: Legacy amc_* token (DB lookup)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Check cache first
    cache_key = f"token_cache:{token_hash}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # Query database
    agent = await db.fetchrow(
        "SELECT id, name, scopes, is_active FROM agents WHERE token_hash = $1",
        token_hash,
    )

    if not agent or not agent["is_active"]:
        raise TokenValidationError("Invalid or inactive agent")

    # Build payload
    payload = {
        "sub": agent["id"],
        "type": "agent",
        "scopes": agent["scopes"] if agent["scopes"] else [],
    }

    # Cache for 5 minutes
    await redis.setex(cache_key, 300, json.dumps(payload))

    return payload
