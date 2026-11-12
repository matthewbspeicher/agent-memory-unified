"""Only storage/paper.py may name a Paper ledger table.

Other modules may join the ledger's transaction for their own tables, but every
statement against a ledger table goes through a PaperStore operation.
"""

import ast
import re
from pathlib import Path

LEDGER_TABLES = (
    "paper_accounts",
    "paper_positions",
    "paper_orders",
    "paper_order_terms",
    "paper_fill_events",
    "paper_risk_events",
    "paper_risk_coverage",
    "paper_dispatches",
    "paper_match_ticks",
)
OWNER = "storage/paper.py"
NOT_PRODUCTION = {"tests", "scratch", "venv", "node_modules", "htmlcov"}
_NAMED = re.compile(r"\b(" + "|".join(LEDGER_TABLES) + r")\b")


def _production_files(root: Path):
    for top in sorted(root.iterdir()):
        if top.name.startswith(".") or top.name in NOT_PRODUCTION:
            continue
        if top.is_file() and top.suffix == ".py":
            yield top
        elif top.is_dir() and not (top / "pyvenv.cfg").exists():
            yield from top.rglob("*.py")


def test_ledger_tables_are_named_only_by_the_paper_store():
    root = Path(__file__).resolve().parents[2]
    assert (root / OWNER).exists()
    violations = []
    for path in _production_files(root):
        relative = path.relative_to(root).as_posix()
        if relative == OWNER:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                match = _NAMED.search(node.value)
                if match:
                    violations.append(f"{relative}:{node.lineno}: {match.group(1)}")
    assert violations == [], "Paper ledger SQL outside the store:\n" + "\n".join(
        violations
    )
