from pydantic import BaseModel, field_validator, model_validator
from decimal import Decimal
from typing import Self


class SymbolSchema(BaseModel):
    ticker: str
    asset_type: str = "STOCK"
    exchange: str | None = None
    currency: str = "USD"
    model_config = {"from_attributes": True}


class AccountSchema(BaseModel):
    account_id: str
    account_type: str = ""
    model_config = {"from_attributes": True}


class PositionSchema(BaseModel):
    symbol: SymbolSchema
    quantity: Decimal
    avg_cost: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    model_config = {"from_attributes": True}


class AccountBalanceSchema(BaseModel):
    account_id: str
    net_liquidation: Decimal
    buying_power: Decimal
    cash: Decimal
    maintenance_margin: Decimal
    model_config = {"from_attributes": True}


class QuoteSchema(BaseModel):
    symbol: SymbolSchema
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    volume: int = 0
    model_config = {"from_attributes": True}


class OrderRequestSchema(BaseModel):
    symbol: SymbolSchema
    side: str
    quantity: Decimal
    account_id: str
    order_type: str = "market"
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    trail_amount: Decimal | None = None
    trail_percent: Decimal | None = None
    time_in_force: str = "DAY"

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        if v.upper() not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        return v.upper()

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v

    @field_validator("limit_price", "stop_price", "trail_amount")
    @classmethod
    def validate_positive_price(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            raise ValueError("price must be positive")
        return v

    @model_validator(mode="after")
    def validate_required_prices(self) -> Self:
        ot = self.order_type.lower()
        if ot == "limit" and self.limit_price is None:
            raise ValueError("limit_price required for limit orders")
        if ot == "stop" and self.stop_price is None:
            raise ValueError("stop_price required for stop orders")
        if ot == "stop_limit" and (self.stop_price is None or self.limit_price is None):
            raise ValueError(
                "stop_price and limit_price required for stop_limit orders"
            )
        if (
            ot == "trailing_stop"
            and self.trail_amount is None
            and self.trail_percent is None
        ):
            raise ValueError(
                "trail_amount or trail_percent required for trailing_stop orders"
            )
        return self


class OrderResultSchema(BaseModel):
    order_id: str
    status: str
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    message: str | None = None
    model_config = {"from_attributes": True}
