from __future__ import annotations

from broker.models import AssetType, Symbol

_UNIVERSES: dict[str, list[str]] = {
    "SP500": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
        "UNH", "LLY", "JPM", "V", "XOM", "MA", "AVGO", "JNJ", "HD", "PG",
        "MRK", "ORCL", "COST", "ABBV", "CVX", "KO", "WMT", "PEP", "BAC",
        "NFLX", "CRM", "TMO", "MCD", "CSCO", "ACN", "LIN", "DHR", "ABT",
        "ADBE", "NKE", "IBM", "NEE", "UPS", "PM", "INTC", "INTU", "AMGN",
        "LOW", "GS", "CAT", "SPGI", "DE",
    ],
    "NASDAQ100": [
        "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL", "GOOG",
        "AVGO", "COST", "NFLX", "ASML", "TMUS", "CSCO", "ADBE", "AMD",
        "PEP", "INTU", "QCOM", "TXN", "AMAT", "HON", "ISRG", "BKNG",
        "VRTX", "SBUX", "GILD", "REGN", "MU", "ADI", "LRCX", "PDD",
        "MRVL", "MNST", "KDP", "KLAC", "SNPS", "CDNS", "ORLY", "CTAS",
        "FTNT", "MAR", "PCAR", "MCHP", "NXPI", "PANW", "WDAY", "DXCM",
        "AZN", "TEAM",
    ],
    "DJIA": [
        "AAPL", "AMGN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
        "DOW", "GS", "HD", "HON", "IBM", "INTC", "JNJ", "JPM", "KO",
        "MCD", "MMM", "MRK", "MSFT", "NKE", "PG", "TRV", "UNH", "V",
        "VZ", "WBA", "WMT",
    ],
}


def get_universe(name: str | list[str]) -> list[Symbol]:
    if isinstance(name, list):
        return [Symbol(ticker=t, asset_type=AssetType.STOCK) for t in name]
    upper = name.upper()
    if upper not in _UNIVERSES:
        raise ValueError(f"Unknown universe: {name}. Known: {list(_UNIVERSES)}")
    return [Symbol(ticker=t, asset_type=AssetType.STOCK) for t in _UNIVERSES[upper]]
