from fastapi import APIRouter, Depends, Query

from api.auth import verify_api_key
from api.deps import get_broker
from api.schemas import QuoteSchema
from broker.interfaces import Broker
from broker.models import Symbol

router = APIRouter(tags=["market_data"])


@router.get("/quotes/{symbol}", response_model=QuoteSchema)
async def get_quote(
    symbol: str,
    _: str = Depends(verify_api_key),
    broker: Broker = Depends(get_broker),
):
    return await broker.market_data.get_quote(Symbol(ticker=symbol))


@router.get("/quotes", response_model=list[QuoteSchema])
async def get_batch_quotes(
    symbols: str = Query(..., description="Comma-separated symbols"),
    _: str = Depends(verify_api_key),
    broker: Broker = Depends(get_broker),
):
    symbol_list = [Symbol(ticker=s.strip()) for s in symbols.split(",")]
    return await broker.market_data.get_quotes(symbol_list)


@router.get("/history/{symbol}")
async def get_historical(
    symbol: str,
    timeframe: str = Query("1 day", description="Bar size"),
    period: str = Query("1 Y", description="Duration"),
    _: str = Depends(verify_api_key),
    broker: Broker = Depends(get_broker),
):
    bars = await broker.market_data.get_historical(
        Symbol(ticker=symbol), timeframe, period
    )
    return [
        {
            "open": str(b.open),
            "high": str(b.high),
            "low": str(b.low),
            "close": str(b.close),
            "volume": b.volume,
            "timestamp": b.timestamp.isoformat(),
        }
        for b in bars
    ]


@router.get("/options/{symbol}/chain")
async def get_options_chain(
    symbol: str,
    expiry: str | None = None,
    _: str = Depends(verify_api_key),
    broker: Broker = Depends(get_broker),
):
    chain = await broker.market_data.get_options_chain(Symbol(ticker=symbol), expiry)
    return {
        "symbol": symbol,
        "expirations": [e.isoformat() for e in chain.expirations],
        "strikes": [str(s) for s in chain.strikes],
    }


@router.get("/contracts/{symbol}")
async def get_contract_details(
    symbol: str,
    _: str = Depends(verify_api_key),
    broker: Broker = Depends(get_broker),
):
    details = await broker.market_data.get_contract_details(Symbol(ticker=symbol))
    return {
        "symbol": {
            "ticker": details.symbol.ticker,
            "asset_type": details.symbol.asset_type.value,
        },
        "long_name": details.long_name,
        "industry": details.industry,
        "category": details.category,
        "min_tick": str(details.min_tick),
        "trading_hours": details.trading_hours,
    }
