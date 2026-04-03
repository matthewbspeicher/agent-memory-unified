from decimal import Decimal
import asyncio
import pytest
from pathlib import Path
import tempfile

from adapters.fidelity.parser import (
    FidelityBalance,
    FidelityPosition,
    _clean_decimal,
    extract_balances,
    normalize_ticker,
    parse_fidelity_csv,
)

SAMPLE_CSV = (
    "Account Number,Account Name,Symbol,Description,Quantity,Last Price,"
    "Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,"
    "Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,"
    "Average Cost Basis,Type\r\n"
    "X12345678,Individual - TOD,SPAXX**,HELD IN MONEY MARKET,,,,\"$5,000.00\",,,,,,,,Cash\r\n"
    "X12345678,Individual - TOD,AAPL,APPLE INC,100,$187.50,+$1.00,\"$18,750.00\",$100.00,0.54%,"
    "+$3,750.00,+25.00%,46.43%,\"$15,000.00\",$150.00,Cash\r\n"
    "X12345678,Individual - TOD,MSFT,MICROSOFT CORP,50,$420.00,-$2.00,\"$21,000.00\",-$100.00,-0.47%,"
    "+$3,000.00,+16.67%,52.00%,\"$18,000.00\",$360.00,Cash\r\n"
    "X87654321,Roth IRA,GOOGL,ALPHABET INC CL A,25,$175.00,-$5.00,\"$4,375.00\",-$125.00,-2.78%,"
    "-$125.00,-2.78%,100.00%,\"$3,500.00\",$140.00,Cash\r\n"
    "\r\n"
    "\"Date downloaded Mar-26-2026 3:37 p.m ET\"\r\n"
)


# ---------------------------------------------------------------------------
# _clean_decimal
# ---------------------------------------------------------------------------

def test_clean_decimal_with_dollar_sign():
    assert _clean_decimal("$1,234.56") == Decimal("1234.56")


def test_clean_decimal_negative():
    assert _clean_decimal("-$500.00") == Decimal("-500.00")


def test_clean_decimal_dash():
    assert _clean_decimal("--") is None


def test_clean_decimal_blank():
    assert _clean_decimal("") is None


# ---------------------------------------------------------------------------
# normalize_ticker
# ---------------------------------------------------------------------------

def test_normalize_ticker():
    assert normalize_ticker("BRK/B") == "BRK.B"
    assert normalize_ticker("SPAXX**") == "SPAXX"
    assert normalize_ticker("AAPL") == "AAPL"
    assert normalize_ticker("CORE**") == "CORE"


# ---------------------------------------------------------------------------
# parse_fidelity_csv
# ---------------------------------------------------------------------------

def test_parse_fidelity_csv():
    positions = parse_fidelity_csv(SAMPLE_CSV)
    assert len(positions) == 3
    symbols = [p.symbol for p in positions]
    assert "SPAXX" not in symbols
    aapl = next(p for p in positions if p.symbol == "AAPL")
    assert aapl.account_id == "X12345678"
    assert aapl.account_name == "Individual - TOD"
    assert aapl.quantity == Decimal("100")
    assert aapl.current_value == Decimal("18750.00")
    googl = next(p for p in positions if p.symbol == "GOOGL")
    assert googl.account_id == "X87654321"


def test_parse_fidelity_csv_empty():
    assert parse_fidelity_csv("") == []


def test_parse_fidelity_csv_no_header():
    # No recognisable header → returns empty list (not an exception)
    result = parse_fidelity_csv("just some random text\nwithout a real header\n")
    assert result == []


def test_parse_fidelity_csv_ticker_normalisation():
    csv = (
        "Account Number,Account Name,Symbol,Description,Quantity,Last Price,"
        "Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,"
        "Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,"
        "Average Cost Basis,Type\r\n"
        'X11111111,Individual,"BRK/B",BERKSHIRE HATHAWAY CL B,10,$450.00,+$1.00,"$4,500.00",'
        '$10.00,0.22%,+$700.00,+18.42%,100.00%,"$3,800.00",$380.00,Cash\r\n'
    )
    positions = parse_fidelity_csv(csv)
    assert len(positions) == 1
    assert positions[0].symbol == "BRK.B"


def test_parse_fidelity_csv_missing_cost_basis():
    """Cost basis may be '--' for transferred positions; quantity/price still parsed."""
    csv = (
        "Account Number,Account Name,Symbol,Description,Quantity,Last Price,"
        "Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,"
        "Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,"
        "Average Cost Basis,Type\r\n"
        'X11111111,Individual,NVDA,NVIDIA CORP,5,$800.00,+$5.00,"$4,000.00",$25.00,0.63%,'
        '--,--,100.00%,--,--,Cash\r\n'
    )
    positions = parse_fidelity_csv(csv)
    assert len(positions) == 1
    assert positions[0].cost_basis is None
    assert positions[0].current_value == Decimal("4000.00")


# ---------------------------------------------------------------------------
# extract_balances
# ---------------------------------------------------------------------------

def test_extract_balances():
    balances = extract_balances(SAMPLE_CSV)
    assert len(balances) == 2
    ind = balances["X12345678"]
    assert ind.cash == Decimal("5000.00")
    assert ind.net_liquidation == Decimal("18750.00") + Decimal("21000.00") + Decimal("5000.00")
    roth = balances["X87654321"]
    assert roth.cash == Decimal("0")
    assert roth.net_liquidation == Decimal("4375.00")


def test_extract_balances_empty():
    assert extract_balances("") == {}


# ---------------------------------------------------------------------------
# FidelityFileWatcher integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_watcher_processes_csv_file():
    """Watcher should import positions and move file to processed/."""
    from unittest.mock import AsyncMock
    from adapters.fidelity.watcher import FidelityFileWatcher

    store = AsyncMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        import_dir = Path(tmpdir)
        csv_path = import_dir / "fidelity_export.csv"
        csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

        watcher = FidelityFileWatcher(store=store, import_dir=str(import_dir), min_age_seconds=0)
        await watcher._scan()

        # File should have been moved to processed/
        remaining = list(import_dir.glob("*.csv"))
        assert remaining == [], f"Expected file to be moved, still found: {remaining}"
        processed = list((import_dir / "processed").glob("*.csv"))
        assert len(processed) == 1

        # import_positions called once per account (2 accounts in SAMPLE_CSV)
        assert store.import_positions.call_count == 2


@pytest.mark.asyncio
async def test_watcher_moves_bad_csv_to_failed():
    """A CSV that fails during store import should land in failed/."""
    from adapters.fidelity.watcher import FidelityFileWatcher
    from unittest.mock import AsyncMock

    store = AsyncMock()
    store.import_positions.side_effect = RuntimeError("DB error")

    with tempfile.TemporaryDirectory() as tmpdir:
        import_dir = Path(tmpdir)
        csv_path = import_dir / "bad.csv"
        csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

        watcher = FidelityFileWatcher(store=store, import_dir=str(import_dir), min_age_seconds=0)
        await watcher._scan()

        remaining = list(import_dir.glob("*.csv"))
        assert remaining == []
        failed_files = list((import_dir / "failed").glob("*.csv"))
        assert len(failed_files) == 1


@pytest.mark.asyncio
async def test_watcher_skips_young_files():
    """Files newer than min_age_seconds should be left untouched."""
    from adapters.fidelity.watcher import FidelityFileWatcher
    from unittest.mock import AsyncMock

    store = AsyncMock()

    with tempfile.TemporaryDirectory() as tmpdir:
        import_dir = Path(tmpdir)
        csv_path = import_dir / "new.csv"
        csv_path.write_text(SAMPLE_CSV, encoding="utf-8")

        watcher = FidelityFileWatcher(store=store, import_dir=str(import_dir), min_age_seconds=9999)
        await watcher._scan()

        # File still present — too young
        assert csv_path.exists()
        store.import_positions.assert_not_called()
