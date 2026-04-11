from fastapi import APIRouter, Depends

from api.auth import verify_api_key
from api.dependencies import get_broker
from api.schemas import (
    AccountSchema,
    PositionSchema,
    AccountBalanceSchema,
    OrderResultSchema,
)
from broker.interfaces import Broker

router = APIRouter(prefix="/engine/v1/trading/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountSchema])
async def list_accounts(
    _: str = Depends(verify_api_key),
    broker: Broker = Depends(get_broker),
):
    return await broker.account.get_accounts()


@router.get("/{account_id}/positions", response_model=list[PositionSchema])
async def get_positions(
    account_id: str,
    _: str = Depends(verify_api_key),
    broker: Broker = Depends(get_broker),
):
    return await broker.account.get_positions(account_id)


@router.get("/{account_id}/balances", response_model=AccountBalanceSchema)
async def get_balances(
    account_id: str,
    _: str = Depends(verify_api_key),
    broker: Broker = Depends(get_broker),
):
    return await broker.account.get_balances(account_id)


@router.get("/{account_id}/orders", response_model=list[OrderResultSchema])
async def get_order_history(
    account_id: str,
    _: str = Depends(verify_api_key),
    broker: Broker = Depends(get_broker),
):
    return await broker.account.get_order_history(account_id)
