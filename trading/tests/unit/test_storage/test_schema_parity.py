"""Schema parity test — catches drift between the two DDL sources.

The trading engine defines its Postgres schema in two places:

1. ``trading/storage/db.py::_INIT_DDL`` + ``init_db_postgres()`` ALTERs — the
   runtime source of truth, applied on every container start.
2. ``scripts/init-trading-tables.sql`` — a snapshot used for manual bootstrap
   (``psql < init-trading-tables.sql``).

Without this test, the two drift. Two prod bugs in one week
(audit_logs, TournamentEngine ``timestamp``) came from columns referenced by
code existing in only one source. This test diffs the effective column set
per table and fails on drift.

See ``feedback_schema_three_sources`` memory entry for the full shape.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
SQL_FILE = REPO_ROOT / "scripts" / "init-trading-tables.sql"
DB_PY = REPO_ROOT / "trading" / "storage" / "db.py"


# Tables owned by a specific module that self-creates them at runtime.
# These are allowed to exist in the SQL file without being in _INIT_DDL.
SELF_CREATED_TABLES = {
    # Created by trading/storage/paper.py on paper broker init
    "paper_accounts",
    "paper_positions",
    "paper_orders",
}

# Tables that are currently known to be dead (defined but never queried).
# Remove from this set once they are either used or purged from the SQL file.
KNOWN_DEAD_TABLES: set[str] = set()


_CREATE_TABLE_RE = re.compile(
    r"CREATE TABLE\s+(?:IF NOT EXISTS\s+)?(\w+)\s*\((.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_ALTER_ADD_COL_RE = re.compile(
    r"ALTER TABLE\s+(\w+)\s+ADD COLUMN\s+(\w+)\s+([A-Z][\w\s]*?)(?:\s+DEFAULT\s+[^,\n]+)?(?=[,\n)])",
    re.IGNORECASE,
)


def _parse_columns(body: str) -> set[str]:
    # Strip SQL line comments first — their contents (especially commas) must
    # not bleed into the column parser.
    body = "\n".join(
        ln for ln in body.splitlines() if not ln.strip().startswith("--")
    )
    cols: set[str] = set()
    depth = 0
    buf = ""
    parts: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
            buf += ch
        elif ch == ")":
            depth -= 1
            buf += ch
        elif ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)

    for raw in parts:
        # Strip SQL line comments so the column keyword is on the first
        # non-comment line.
        stripped_lines = [
            ln for ln in raw.splitlines() if not ln.strip().startswith("--")
        ]
        line = "\n".join(stripped_lines).strip()
        if not line:
            continue
        upper = line.upper()
        # Skip table-level constraints
        if upper.startswith(
            ("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CONSTRAINT", "CHECK")
        ):
            continue
        m = re.match(r'"?(\w+)"?\s', line)
        if m:
            cols.add(m.group(1).lower())
    return cols


def _extract_sql_schema(text: str) -> dict[str, set[str]]:
    schema: dict[str, set[str]] = {}
    for m in _CREATE_TABLE_RE.finditer(text):
        table = m.group(1).lower()
        schema.setdefault(table, set()).update(_parse_columns(m.group(2)))
    return schema


def _extract_python_schema(text: str) -> dict[str, set[str]]:
    """Extract schema from _INIT_DDL string + _migrations ALTER list.

    Also picks up additional CREATE TABLE calls that are embedded in
    ``init_db_postgres()`` (e.g. ``thought_records``) by scanning the whole
    file for CREATE TABLE patterns inside triple-quoted strings.
    """
    # Pull _INIT_DDL contents
    init_match = re.search(r'_INIT_DDL\s*=\s*"""(.*?)"""', text, re.DOTALL)
    init_ddl = init_match.group(1) if init_match else ""

    # Pull every CREATE TABLE block from the whole file (covers thought_records
    # etc. created in init_db_postgres).
    all_sources = text

    schema = _extract_sql_schema(all_sources)
    # init_ddl is already a subset of all_sources, so above already covers it.
    _ = init_ddl

    # Apply _migrations ALTER ADD COLUMN entries — parsed from the
    # ``_migrations = [...]`` literal inside init_db_postgres.
    mig_block = re.search(
        r"_migrations\s*=\s*\[(.*?)\]", text, re.DOTALL
    )
    if mig_block:
        tuple_re = re.compile(
            r'\(\s*"(\w+)"\s*,\s*"(\w+)"\s*,\s*"([^"]+)"\s*\)'
        )
        for m in tuple_re.finditer(mig_block.group(1)):
            table = m.group(1).lower()
            col = m.group(2).lower()
            schema.setdefault(table, set()).add(col)

    # Apply loose ALTER TABLE ... ADD COLUMN statements executed elsewhere in
    # the file.
    for m in _ALTER_ADD_COL_RE.finditer(text):
        schema.setdefault(m.group(1).lower(), set()).add(m.group(2).lower())

    return schema


def _load_sources() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    sql_text = SQL_FILE.read_text()
    py_text = DB_PY.read_text()
    return _extract_sql_schema(sql_text), _extract_python_schema(py_text)


def test_every_python_table_is_in_sql_file() -> None:
    """Every table created at runtime must also be in the SQL bootstrap file.

    Exception: self-created tables owned by specific modules (paper broker).
    """
    _sql, py = _load_sources()
    sql_tables = set(_sql.keys())
    py_tables = set(py.keys())
    missing = py_tables - sql_tables - SELF_CREATED_TABLES
    assert not missing, (
        f"Tables created in Python but missing from init-trading-tables.sql: "
        f"{sorted(missing)}. A manual `psql < init-trading-tables.sql` "
        f"bootstrap would skip these."
    )


def test_every_sql_table_is_either_in_python_or_self_created() -> None:
    """Every table in the SQL file must be created by Python or by a module.

    If a table is in the SQL file but nothing creates it at runtime, it's
    dead weight that silently rots.
    """
    sql, py = _load_sources()
    sql_tables = set(sql.keys())
    py_tables = set(py.keys())
    orphaned = sql_tables - py_tables - SELF_CREATED_TABLES - KNOWN_DEAD_TABLES
    assert not orphaned, (
        f"Tables in init-trading-tables.sql with no runtime creator: "
        f"{sorted(orphaned)}. Either wire them into Python DDL, confirm a "
        f"module self-creates them (then add to SELF_CREATED_TABLES), or "
        f"delete them."
    )


def test_every_python_column_exists_in_sql_file() -> None:
    """Every column Python creates must exist in the SQL bootstrap file.

    This catches the shape of the TournamentEngine/audit_logs prod bugs: a
    column referenced by code (via _INIT_DDL or _migrations) doesn't exist
    in init-trading-tables.sql, so manual bootstrap paths break.

    One-directional: SQL file may have extra columns (e.g. Laravel-era
    created_at/updated_at) — those are harmless. Only Python-has-it /
    SQL-lacks-it is a prod risk.
    """
    sql, py = _load_sources()
    common = set(sql.keys()) & set(py.keys())

    diffs: list[str] = []
    for table in sorted(common):
        missing_in_sql = py[table] - sql[table]
        if missing_in_sql:
            diffs.append(f"  {table}: missing={sorted(missing_in_sql)}")

    assert not diffs, (
        "Columns present in Python DDL but missing from "
        "init-trading-tables.sql:\n"
        + "\n".join(diffs)
        + "\n\nAdd these columns to scripts/init-trading-tables.sql. The "
        "Python side (trading/storage/db.py::_INIT_DDL + _migrations) is "
        "the runtime source of truth."
    )
