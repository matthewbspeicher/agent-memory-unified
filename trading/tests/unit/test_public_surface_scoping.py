"""Ensures trading/api/routes/public.py cannot call mutation methods.

Fails if any forbidden method name is invoked inside the file.
"""

import ast
from pathlib import Path

FORBIDDEN_METHOD_NAMES = {
    "execute_trade",
    "place_order",
    "cancel_order",
    "modify_order",
    "stop_agent",
    "start_agent",
    "evolve",
    "scan",
    "kill_switch",
    "activate_kill_switch",
    "deactivate",
    "add_entity",
    "add_triple",
    "invalidate",
    "update_weights",
    "set_weights",
    "store",
    "write",
    "delete",
    "remove",
    "create",
    "register",
    "promote",
    "settle",
    "breed",
    "approve",
    "reject",
    "tune",
    "transition",
}

ALLOWED_EXCEPTIONS = {
    "get_current_match_public",
    "get_current_season_public",
    "get_top_leaderboard",
    "get_leaderboard",
    "query_entity_public",
    "timeline_public",
    "_base_response",
}


def test_public_py_calls_no_mutation_methods():
    public_py = Path(__file__).parent.parent.parent / "api" / "routes" / "public.py"
    assert public_py.exists(), f"Missing {public_py}"

    tree = ast.parse(public_py.read_text())
    forbidden_calls = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                method_name = node.func.id
            else:
                continue

            if method_name in ALLOWED_EXCEPTIONS:
                continue
            if method_name in FORBIDDEN_METHOD_NAMES:
                forbidden_calls.append((node.lineno, method_name))

    assert not forbidden_calls, (
        f"public.py calls forbidden mutation methods: {forbidden_calls}. "
        f"Public surface must be read-only."
    )


def test_public_py_has_no_api_key_dependencies():
    public_py = Path(__file__).parent.parent.parent / "api" / "routes" / "public.py"
    content = public_py.read_text()
    assert "verify_api_key" not in content, "public.py must not import verify_api_key"
    assert "require_scope" not in content, "public.py must not import require_scope"
