"""Token generation, hashing, and verification primitives for agent identity."""

from __future__ import annotations

import hashlib
import os
import secrets
import base64

TOKEN_PREFIX = "amu_"


def generate_token() -> str:
    """Generate a new agent token with prefix and sufficient entropy."""
    random_bytes = secrets.token_bytes(32)
    encoded = base64.urlsafe_b64encode(random_bytes).rstrip(b"=").decode("ascii")
    return f"{TOKEN_PREFIX}{encoded}"


def hash_token(token: str) -> str:
    """Hash a token with a random salt for secure storage.

    Returns format: salt_hex$digest_hex
    """
    salt = secrets.token_bytes(16)
    salt_hex = salt.hex()
    digest = hashlib.sha256(salt + token.encode()).hexdigest()
    return f"{salt_hex}${digest}"


def verify_token(token: str, stored_hash: str) -> bool:
    """Verify a token against its stored hash.

    Args:
        token: The plain token to verify
        stored_hash: The stored hash in format "salt_hex$digest_hex"

    Returns:
        True if token matches, False otherwise
    """
    if "$" not in stored_hash:
        return False
    try:
        salt_hex, expected_digest = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        actual_digest = hashlib.sha256(salt + token.encode()).hexdigest()
        return secrets.compare_digest(actual_digest, expected_digest)
    except (ValueError, TypeError):
        return False
