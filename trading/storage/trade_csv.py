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


TAX_HEADERS = [
    "Description of property",
    "Date acquired",
    "Date sold",
    "Proceeds",
    "Cost or other basis",
    "Gain or (loss)",
    "Code",
    "Adjustments",
    "Wash sale loss disallowed",
]


class TaxExporter:
    """Export trade_analytics data as Form 8949-compatible CSV."""

    def __init__(self, db):
        self._db = db

    async def export_tax_report(
        self,
        year: int,
        agent_name: str | None = None,
        output_path: str | None = None,
    ) -> str:
        """Query trade_analytics and write Form 8949 CSV. Returns file path."""
        query = """
            SELECT symbol, entry_time, exit_time,
                   entry_price, exit_price, entry_quantity,
                   entry_fees, exit_fees, net_pnl, hold_minutes
            FROM trade_analytics
            WHERE exit_time >= ? AND exit_time < ?
              AND status = 'closed'
        """
        params: list = [f"{year}-01-01", f"{year + 1}-01-01"]

        if agent_name:
            query += " AND agent_name = ?"
            params.append(agent_name)

        query += " ORDER BY exit_time ASC"

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()

        path = output_path or f"tax_report_{year}.csv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(TAX_HEADERS)

            for row in rows:
                (
                    symbol,
                    entry_time,
                    exit_time,
                    entry_price,
                    exit_price,
                    quantity,
                    entry_fees,
                    exit_fees,
                    net_pnl,
                    hold_minutes,
                ) = row

                cost_basis = (
                    Decimal(str(entry_price)) * Decimal(str(quantity))
                ) + Decimal(str(entry_fees or 0))
                proceeds = Decimal(str(exit_price)) * Decimal(str(quantity))
                gain_loss = proceeds - cost_basis

                days_held = Decimal(str(hold_minutes or 0)) / Decimal("1440")
                holding_code = "S" if days_held < 365 else "L"

                entry_date = str(entry_time)[:10] if entry_time else ""
                exit_date = str(exit_time)[:10] if exit_time else ""

                writer.writerow(
                    [
                        symbol,
                        entry_date,
                        exit_date,
                        f"{proceeds:.2f}",
                        f"{cost_basis:.2f}",
                        f"{gain_loss:.2f}",
                        holding_code,
                        "",
                        "",
                    ]
                )

        logger.info("Tax report %s: %d trades exported", path, len(rows))
        return path
