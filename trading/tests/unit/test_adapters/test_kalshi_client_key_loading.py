"""KalshiClient private-key loading — path vs inline PEM."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.kalshi.client import KalshiClient


@pytest.fixture
def pem_material(tmp_path: Path) -> tuple[Path, str]:
    pem = "-----BEGIN PRIVATE KEY-----\nAAAAFAKEFAKEFAKE\n-----END PRIVATE KEY-----\n"
    pem_file = tmp_path / "kalshi.pem"
    pem_file.write_text(pem)
    return pem_file, pem


def test_loads_private_key_from_path(pem_material: tuple[Path, str]) -> None:
    pem_file, pem = pem_material
    client = KalshiClient(key_id="k", private_key_path=str(pem_file), demo=True)
    try:
        assert client._private_key == pem
    finally:
        # Avoid leaking the httpx client across tests.
        import asyncio

        asyncio.run(client.close())


def test_loads_private_key_from_pem_arg(pem_material: tuple[Path, str]) -> None:
    _, pem = pem_material
    client = KalshiClient(key_id="k", private_key_pem=pem, demo=True)
    try:
        assert client._private_key == pem
    finally:
        import asyncio

        asyncio.run(client.close())


def test_pem_arg_takes_precedence_over_path(
    pem_material: tuple[Path, str], tmp_path: Path
) -> None:
    _, inline_pem = pem_material
    other = tmp_path / "other.pem"
    other.write_text("-----BEGIN OTHER-----\n")
    client = KalshiClient(
        key_id="k",
        private_key_path=str(other),
        private_key_pem=inline_pem,
        demo=True,
    )
    try:
        assert client._private_key == inline_pem
    finally:
        import asyncio

        asyncio.run(client.close())


def test_no_key_material_leaves_private_key_none() -> None:
    client = KalshiClient(key_id="k", demo=True)
    try:
        assert client._private_key is None
    finally:
        import asyncio

        asyncio.run(client.close())
