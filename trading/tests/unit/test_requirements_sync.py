"""Catch drift between pyproject.toml and requirements.txt.

Every direct dep declared in `pyproject.toml [project].dependencies`
must also appear (with a compatible version spec) in `requirements.txt`.
If it doesn't, CI — which runs `pip install -r requirements.txt` —
fails at test collection with `ModuleNotFoundError` for packages the
app imports.

This has bitten us twice in one session: `bcrypt`/`passlib`/`ulid-py`
were in pyproject.toml but missing from requirements.txt, and CI
failed to even collect the test suite. This test would have caught
both before the push.

Skips when either file isn't reachable (e.g. Docker test container
without the repo root mounted). That case is separately covered by
test_schema_parity's module-level skip pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Both files live at trading/ root — not at repo root. __file__ is
# trading/tests/unit/test_requirements_sync.py, so parents[2] = trading/.
TRADING_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_TOML = TRADING_ROOT / "pyproject.toml"
REQUIREMENTS_TXT = TRADING_ROOT / "requirements.txt"

if not PYPROJECT_TOML.exists() or not REQUIREMENTS_TXT.exists():
    pytest.skip(
        "pyproject.toml or requirements.txt not reachable from the test "
        "runner (e.g. container mount missing) — environment issue, not "
        "a sync regression",
        allow_module_level=True,
    )


# Names sometimes differ between PyPI package names and pyproject keys
# (e.g. `PyJWT` vs `pyjwt`). Normalise to lowercase + strip common
# suffixes before comparing.
def _normalize_name(raw: str) -> str:
    return raw.strip().lower().replace("_", "-")


def _parse_pyproject_deps(path: Path) -> tuple[set[str], set[str]]:
    """Extract deps from pyproject.toml. Returns (direct, all_including_extras).

    Parses the multiline-array shape this repo uses for both
    `[project].dependencies = [...]` and each group under
    `[project.optional-dependencies]`. The forward check below uses
    `direct` (must-have-in-requirements); the reverse check uses the
    union (since requirements.txt legitimately carries test extras like
    pytest, which live in `[project.optional-dependencies].test`).
    """
    direct: set[str] = set()
    extras: set[str] = set()
    in_direct = False
    in_optional_group = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("dependencies = ["):
            in_direct = True
            continue
        if line.startswith("[project.optional-dependencies]"):
            # From now until the next top-level [section], any `group = [`
            # line opens an extras group.
            continue
        if line.startswith("[") and not line.startswith("[project."):
            in_direct = False
            in_optional_group = False
            continue
        # Match `<group> = [` inside [project.optional-dependencies]
        if not in_direct and not in_optional_group and "= [" in line:
            in_optional_group = True
            continue
        if in_direct or in_optional_group:
            if line.startswith("]"):
                in_direct = False
                in_optional_group = False
                continue
            if not line or line.startswith("#"):
                continue
            inner = line.strip("\",' ")
            name = re.split(r"[<>=!~;\[]", inner)[0]
            if name:
                normalized = _normalize_name(name)
                if in_direct:
                    direct.add(normalized)
                else:
                    extras.add(normalized)
    return direct, direct | extras


def _parse_requirements(path: Path) -> set[str]:
    """Extract the non-commented direct deps from requirements.txt."""
    names: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip inline comments (e.g. `pkg==1.2  # note`).
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name = re.split(r"[<>=!~;\[]", line)[0]
        if name:
            names.add(_normalize_name(name))
    return names


def test_every_pyproject_direct_dep_is_in_requirements():
    """Forward check: every [project].dependencies entry must appear in
    requirements.txt. CI's `pip install -r requirements.txt` fails at
    import-time if a package app code depends on isn't listed."""
    direct, _all = _parse_pyproject_deps(PYPROJECT_TOML)
    reqs = _parse_requirements(REQUIREMENTS_TXT)
    assert direct, (
        "parser returned zero direct deps from pyproject.toml — did "
        "the file format change? This parser handles the multiline "
        "[project].dependencies list shape."
    )
    missing = direct - reqs
    assert not missing, (
        "Deps in pyproject.toml [project].dependencies but NOT in "
        f"requirements.txt: {sorted(missing)}. Add them to "
        "requirements.txt (keep version spec compatible with pyproject)."
    )


def test_every_requirement_is_declared_somewhere_in_pyproject():
    """Reverse check: every requirements.txt entry must be declared
    somewhere in pyproject.toml — either [project].dependencies or any
    [project.optional-dependencies].<group>. Catches drift in the
    other direction (dep removed from pyproject but left dangling in
    requirements). Accepts optional extras because requirements.txt
    legitimately bundles test deps like pytest which live under
    [project.optional-dependencies].test in pyproject.
    """
    _direct, all_declared = _parse_pyproject_deps(PYPROJECT_TOML)
    reqs = _parse_requirements(REQUIREMENTS_TXT)
    extras = reqs - all_declared
    assert not extras, (
        f"Deps in requirements.txt but NOT declared anywhere in "
        f"pyproject.toml: {sorted(extras)}. Add them to "
        "[project].dependencies (if core) or a "
        "[project.optional-dependencies].<group> (if extras), or "
        "remove from requirements.txt if dead."
    )
