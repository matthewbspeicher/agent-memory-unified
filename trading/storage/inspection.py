"""Read-only structure inspection shared by storage owners."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckIssue:
    name: str
    error_type: str


async def inspect_tables(db, tables) -> tuple[CheckIssue, ...]:
    """Read explicit columns without rows, writes, initialization or admission locks."""
    issues = []
    for table, columns in tables.items():
        try:
            async with db.execute(
                f"SELECT {', '.join(columns.split())} FROM {table} WHERE 1=0"
            ) as cursor:
                await cursor.fetchall()
        except Exception as error:
            issues.append(CheckIssue(table, type(error).__name__))
    return tuple(issues)
