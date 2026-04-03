from __future__ import annotations
from dataclasses import dataclass


KNOWN_COMMANDS = {
    "portfolio", "opportunities", "agents", "kill", "unkill",
    "approve", "reject", "buy", "sell", "chart", "start", "stop", "help",
    "pnl", "performance", "trust", "optimize", "tournament", "import", "markets",
    "rank", "journal", "brief", "warroom", "backtest", "regime", "paper",
}


@dataclass
class Command:
    name: str
    args: list[str]


def parse_command(text: str) -> Command | None:
    text = text.strip()
    if not text.startswith("/"):
        return None

    parts = text[1:].split()
    if not parts:
        return None

    name = parts[0].lower()
    if name not in KNOWN_COMMANDS:
        return None

    return Command(name=name, args=parts[1:])
