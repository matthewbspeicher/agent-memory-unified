import json
import re
from pathlib import Path

MANIFEST_PATH = Path(__file__).parent.parent.parent / "public_content" / "agents.json"
PUBLIC_PY_PATH = Path(__file__).parent.parent.parent / "api" / "routes" / "public.py"


def test_agents_json_is_valid():
    assert MANIFEST_PATH.exists(), f"Missing {MANIFEST_PATH}"
    data = json.loads(MANIFEST_PATH.read_text())
    assert data["schema_version"] == "1.0"
    assert data["name"] == "agent-memory-unified"
    assert "endpoints" in data
    assert len(data["endpoints"]) > 0


def test_agents_json_endpoints_match_routes():
    data = json.loads(MANIFEST_PATH.read_text())
    manifest_paths = {e["path"] for e in data["endpoints"]}

    public_content = PUBLIC_PY_PATH.read_text()
    route_matches = re.findall(r'@router\.get\("([^"]+)"', public_content)
    actual_paths = {
        f"/engine/v1/public{p}" if not p.startswith("/engine") else p
        for p in route_matches
    }

    missing_in_manifest = actual_paths - manifest_paths
    extra_in_manifest = manifest_paths - actual_paths

    assert not missing_in_manifest, (
        f"agents.json is missing these routes: {missing_in_manifest}. "
        f"Update trading/public_content/agents.json to match."
    )
    assert not extra_in_manifest, (
        f"agents.json lists these routes that don't exist in public.py: {extra_in_manifest}. "
        f"Either add the routes or remove from the manifest."
    )
