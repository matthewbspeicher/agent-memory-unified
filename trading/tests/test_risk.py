import json
from pathlib import Path

from risk.pnl import compute_child_pnl


def test_compute_child_pnl_matches_php():
    """
    Reads math_vectors.json and verifies compute_child_pnl outputs match exactly
    the expected_net_pnl and expected_pnl_percent from PHP bcmath.
    """
    # Locate the shared/tests/math_vectors.json file
    # Assuming tests run from the trading directory or project root
    current_dir = Path(__file__).resolve().parent

    # Traverse up to find the project root (where `shared/` lives)
    # project_root/trading/tests/test_risk.py
    project_root = current_dir.parent.parent
    json_path = project_root / "shared" / "tests" / "math_vectors.json"

    with open(json_path, "r") as f:
        vectors = json.load(f)

    for idx, vector in enumerate(vectors):
        result = compute_child_pnl(
            child_entry=vector["child_entry"],
            parent_entry=vector["parent_entry"],
            child_qty=vector["child_quantity"],
            parent_qty=vector["parent_quantity"],
            parent_direction=vector["parent_direction"],
            parent_fees=vector["parent_fees"],
            child_fees=vector["child_fees"],
        )

        assert result["pnl"] == vector["expected_net_pnl"], (
            f"Mismatch in PnL for vector {idx} ({vector['description']}): Expected {vector['expected_net_pnl']}, got {result['pnl']}"
        )
        assert result["pnl_percent"] == vector["expected_pnl_percent"], (
            f"Mismatch in PnL percent for vector {idx} ({vector['description']}): Expected {vector['expected_pnl_percent']}, got {result['pnl_percent']}"
        )
