"""Register exception handlers for broker-specific errors."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from broker.errors import (
    BrokerConnectionError,
    BrokerError,
    InsufficientFunds,
    InvalidSymbol,
    MarketClosed,
    OrderRejected,
    RateLimitExceeded,
)


def register_error_handlers(app: FastAPI) -> None:
    """Register exception handlers for broker domain errors."""

    @app.exception_handler(BrokerConnectionError)
    async def broker_connection_error_handler(
        request: Request, exc: BrokerConnectionError
    ):
        return JSONResponse(
            status_code=503, content={"detail": str(exc)}, headers={"Retry-After": "5"}
        )

    @app.exception_handler(InvalidSymbol)
    async def invalid_symbol_handler(request: Request, exc: InvalidSymbol):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(InsufficientFunds)
    async def insufficient_funds_handler(request: Request, exc: InsufficientFunds):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(MarketClosed)
    async def market_closed_handler(request: Request, exc: MarketClosed):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(OrderRejected)
    async def order_rejected_handler(request: Request, exc: OrderRejected):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        return JSONResponse(status_code=429, content={"detail": str(exc)})

    @app.exception_handler(BrokerError)
    async def broker_error_handler(request: Request, exc: BrokerError):
        return JSONResponse(
            status_code=502, content={"detail": "Broker error occurred"}
        )
