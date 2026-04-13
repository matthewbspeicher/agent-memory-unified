"""Ensures no public endpoint response can leak secrets."""

import re
from fastapi.testclient import TestClient
from api.app import create_app


FORBIDDEN_SUBSTRINGS = [
    "STA_",
    "B64_",
    "api_key",
    "apikey",
    "secret",
    "password",
    "coldkey",
    "hotkey",
    "wallet",
    "private_key",
    "bearer ",
    "Authorization",
]

PUBLIC_ENDPOINTS = [
    "/engine/v1/public/status",
    "/engine/v1/public/agents",
    "/engine/v1/public/arena/state",
    "/engine/v1/public/leaderboard",
    "/engine/v1/public/kg/entity/BTC",
    "/engine/v1/public/kg/timeline",
    "/engine/v1/public/milestones",
    "/engine/v1/public/agents.json",
]


def test_no_public_endpoint_leaks_secrets():
    app = create_app()
    client = TestClient(app)

    leaks = []
    for path in PUBLIC_ENDPOINTS:
        resp = client.get(path)
        body = resp.text.lower()
        for forbidden in FORBIDDEN_SUBSTRINGS:
            if forbidden.lower() in body:
                if forbidden == "api_key" and '"api_key_header"' in resp.text:
                    continue
                if forbidden == "bearer " and "bearer token" in body:
                    continue
                leaks.append((path, forbidden))

    assert not leaks, f"Public endpoints leaked forbidden substrings: {leaks}"
