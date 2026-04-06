"""
Fidelity CSV position parser.

Handles the real Fidelity "Portfolio_Positions" CSV export format:
  Account Number,Account Name,Symbol,Description,Quantity,Last Price,...

Key quirks:
- No title row — header is the very first line
- Money-market rows (SPAXX**, CORE**, FCASH**, USD***) have blank/-- qty & price
- Cash-equivalent symbols end with ** or ***
- Some rows have ISIN-style tickers (e.g. G0223V105) — kept as-is
- "Pending activity" rows must be skipped (no symbol)
- Quantity can be a decimal (fractional shares in IRAs/retirement accounts)
- Price/value fields are prefixed with $ and use commas (e.g. $1,234.56)
- Negative values are prefixed -$ (e.g. -$25.00)
- Footer rows starting with " (disclaimer text) should be skipped
- BRK/B → BRK.B normalisation for IBKR compatibility
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

# Symbols that represent cash equivalents (money market, USD holdings)
_CASH_SYMBOLS = {"SPAXX", "CORE", "FCASH", "USD"}

# Rows with these account names are crypto-only accounts — skip position creation
_SKIP_ACCOUNT_NAMES = {"OLD Crypto - dupe", "Fidelity Crypto®"}


@dataclass
class FidelityPosition:
    account_id: str
    account_name: str
    symbol: str
    description: str
    quantity: Decimal
    last_price: Decimal
    current_value: Decimal
    cost_basis: Decimal | None
    cost_basis_per_share: Decimal | None


@dataclass
class FidelityBalance:
    account_id: str
    account_name: str
    net_liquidation: Decimal
    cash: Decimal


def normalize_ticker(symbol: str) -> str:
    """Normalise a Fidelity ticker to IBKR-compatible form."""
    symbol = symbol.rstrip("*")  # strip trailing * (SPAXX**, USD***)
    symbol = symbol.replace("/", ".")  # BRK/B → BRK.B
    return symbol


def _is_cash_equivalent(raw_symbol: str) -> bool:
    """Return True if this symbol represents a cash/money-market holding."""
    normalized = normalize_ticker(raw_symbol)
    return (
        normalized in _CASH_SYMBOLS
        or raw_symbol.endswith("**")
        or raw_symbol.endswith("***")
    )


def _clean_decimal(value: str) -> Decimal | None:
    """Parse a Fidelity formatted number (e.g. '$1,234.56', '-$25.00', '--') to Decimal."""
    value = value.strip()
    if not value or value in ("--", "n/a", "N/A"):
        return None
    # Remove currency prefix and comma separators; preserve minus sign
    value = value.replace("$", "").replace(",", "").replace("+", "")
    try:
        return Decimal(value)
    except Exception:
        return None


def _find_header_row(lines: list[str]) -> int | None:
    """Return index of the row containing 'Account Number' or 'Account Name/Number'."""
    for i, line in enumerate(lines):
        stripped = line.strip().strip('"')
        if "Account Number" in stripped or "Account Name/Number" in stripped:
            return i
    return None


def _iter_data_rows(file_content: str):
    """Yield DictReader rows from the positions section of the CSV."""
    # Normalise line endings
    content = file_content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.splitlines()

    header_idx = _find_header_row(lines)
    if header_idx is None:
        return  # no header found — empty or unrecognised format

    csv_text = "\n".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(csv_text))

    for row in reader:
        # Skip blank rows (all values empty)
        if not any(v.strip() for v in row.values() if v):
            continue

        # Skip footer / disclaimer rows
        raw_symbol = ""
        # Handle both "Symbol" column name variants
        if "Symbol" in row:
            raw_symbol = (row.get("Symbol") or "").strip()
        if not raw_symbol:
            continue

        # Skip pending-activity pseudo-rows
        if raw_symbol.lower() in ("pending activity", "pending_activity"):
            continue

        yield row


def parse_fidelity_csv(file_content: str) -> list[FidelityPosition]:
    """
    Parse a Fidelity positions CSV and return non-cash positions.

    Skips:
    - Money-market / cash-equivalent symbols (SPAXX**, CORE**, USD***)
    - Pending activity rows
    - Rows from crypto-only accounts
    - Rows with no parseable quantity or price
    """
    positions: list[FidelityPosition] = []

    for row in _iter_data_rows(file_content):
        raw_symbol = (row.get("Symbol") or "").strip()

        # Resolve account identifiers — handle both CSV variants
        account_id = (
            row.get("Account Number") or row.get("Account Name/Number", "")
        ).strip()
        account_name = (row.get("Account Name") or "").strip()

        # Skip crypto-only accounts
        if account_name in _SKIP_ACCOUNT_NAMES:
            continue

        # Skip cash equivalents
        if _is_cash_equivalent(raw_symbol):
            continue

        normalized = normalize_ticker(raw_symbol)

        quantity = _clean_decimal(row.get("Quantity", "") or "")
        last_price = _clean_decimal(row.get("Last Price", "") or "")
        current_value = _clean_decimal(row.get("Current Value", "") or "")

        # Must have at minimum a valid quantity and current value to be useful
        if quantity is None or current_value is None:
            logger.debug("Skipping %s — no quantity or value", raw_symbol)
            continue

        # Synthesise last_price from current_value / quantity if missing
        if last_price is None and quantity != 0:
            last_price = current_value / quantity

        positions.append(
            FidelityPosition(
                account_id=account_id,
                account_name=account_name,
                symbol=normalized,
                description=(row.get("Description") or "").strip(),
                quantity=quantity,
                last_price=last_price or Decimal("0"),
                current_value=current_value,
                cost_basis=_clean_decimal(row.get("Cost Basis Total", "") or ""),
                cost_basis_per_share=_clean_decimal(
                    row.get("Average Cost Basis")
                    or row.get("Cost Basis Per Share", "")
                    or ""
                ),
            )
        )

    return positions


def extract_balances(file_content: str) -> dict[str, FidelityBalance]:
    """
    Extract per-account balances from a Fidelity positions CSV.

    Net liquidation = sum of all Current Value for the account.
    Cash = sum of Current Value for cash-equivalent symbols only.
    """
    balances: dict[str, FidelityBalance] = {}

    for row in _iter_data_rows(file_content):
        raw_symbol = (row.get("Symbol") or "").strip()

        account_id = (
            row.get("Account Number") or row.get("Account Name/Number", "")
        ).strip()
        account_name = (row.get("Account Name") or "").strip()

        # Skip crypto-only accounts
        if account_name in _SKIP_ACCOUNT_NAMES:
            continue

        current_value = _clean_decimal(row.get("Current Value", "") or "") or Decimal(
            "0"
        )

        # Skip rows with no value contribution (e.g. Pending activity, ISIN with --)
        if current_value == 0 and not _is_cash_equivalent(raw_symbol):
            try:
                # Pending activity rows often have a negative "Current Value"
                pending_val = _clean_decimal(row.get("Current Value", "") or "")
                if pending_val is None:
                    continue
                current_value = pending_val
            except Exception:
                continue

        if account_id not in balances:
            balances[account_id] = FidelityBalance(
                account_id=account_id,
                account_name=account_name,
                net_liquidation=Decimal("0"),
                cash=Decimal("0"),
            )

        bal = balances[account_id]
        is_cash = _is_cash_equivalent(raw_symbol)

        # For positions with unknown value (--), don't add/subtract
        try:
            balances[account_id] = FidelityBalance(
                account_id=bal.account_id,
                account_name=bal.account_name,
                net_liquidation=bal.net_liquidation + current_value,
                cash=bal.cash + current_value if is_cash else bal.cash,
            )
        except Exception:
            pass

    return balances
