from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TradeCSVLogger:
    CSV_FILE = "trades.csv"
    HEADERS = [
        "Date",
        "Time (UTC)",
        "Exchange",
        "Symbol",
        "Side",
        "Quantity",
        "Price",
        "Total USD",
        "Fee (est.)",
        "Net Amount",
        "Order ID",
        "Mode",
        "Notes",
    ]

    def __init__(self, output_dir: str = "."):
        self.output_path = Path(output_dir) / self.CSV_FILE

    def _ensure_file(self) -> None:
        if not self.output_path.exists():
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.HEADERS)

    def log_trade(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        exchange: str,
        order_id: str,
        mode: str,
        notes: str = "",
        fee_estimate: Decimal | None = None,
    ) -> None:
        self._ensure_file()

        now = datetime.now(timezone.utc)
        date = now.strftime("%Y-%m-%d")
        time = now.strftime("%H:%M:%S")

        total = quantity * price
        fee = fee_estimate or total * Decimal("0.001")
        net = total - fee

        row = [
            date,
            time,
            exchange,
            symbol,
            side,
            f"{quantity:.6f}",
            f"{price:.2f}",
            f"{total:.2f}",
            f"{fee:.4f}",
            f"{net:.2f}",
            order_id,
            mode,
            f'"{notes}"' if notes else "",
        ]

        with open(self.output_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)

        logger.info("Tax record saved to %s", self.output_path)

    def log_blocked(
        self,
        symbol: str,
        exchange: str,
        reason: str,
        notes: str = "",
    ) -> None:
        self._ensure_file()

        now = datetime.now(timezone.utc)
        date = now.strftime("%Y-%m-%d")
        time = now.strftime("%H:%M:%S")

        row = [
            date,
            time,
            exchange,
            symbol,
            "BLOCKED",
            "",
            "",
            "",
            "",
            "",
            "BLOCKED",
            "BLOCKED",
            f'"Failed: {reason}. {notes}"',
        ]

        with open(self.output_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)

        logger.info("Blocked trade logged to %s", self.output_path)

    def generate_summary(self) -> dict[str, Any]:
        if not self.output_path.exists():
            return {
                "total_decisions": 0,
                "live_trades": 0,
                "paper_trades": 0,
                "blocked": 0,
                "total_volume": Decimal("0"),
                "total_fees": Decimal("0"),
            }

        with open(self.output_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        live = [r for r in rows if r.get("Mode") == "LIVE"]
        paper = [r for r in rows if r.get("Mode") == "PAPER"]
        blocked = [r for r in rows if r.get("Mode") == "BLOCKED"]

        total_volume = sum(Decimal(r.get("Total USD", "0") or "0") for r in live)
        total_fees = sum(Decimal(r.get("Fee (est.)", "0") or "0") for r in live)

        return {
            "total_decisions": len(rows),
            "live_trades": len(live),
            "paper_trades": len(paper),
            "blocked": len(blocked),
            "total_volume": total_volume,
            "total_fees": total_fees,
        }
