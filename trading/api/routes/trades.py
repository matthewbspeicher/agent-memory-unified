# api/routes/trades.py
"""
Trade history endpoints with hybrid authentication.

Agents can list their own trades, view specific trades, and create new trades.
Requires JWT or legacy amc_* token for authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional

from api.dependencies import get_current_user, check_kill_switch
from storage.trades import TradeStore
from utils.audit import audit_event

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("")
async def list_trades(
    request: Request,
    status: Optional[str] = None,
    limit: int = 50,
    user: dict = Depends(get_current_user),
):
    """List all trades for the authenticated agent.

    Args:
        status: Optional filter by trade status
        limit: Maximum number of trades to return (default: 50)
        user: Authenticated user from JWT or legacy token

    Returns:
        List of trade records
    """
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    agent_id = user["sub"]
    store = TradeStore(db)

    # Get trades for this agent
    trades = await store.get_trades(agent_name=agent_id, limit=limit)

    # Filter by status if provided
    if status:
        trades = [t for t in trades if t.get("status") == status]

    return trades


@router.get("/{trade_id}")
async def get_trade(
    trade_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Get details of a specific trade.

    Args:
        trade_id: The trade ID (opportunity_id in current schema)
        user: Authenticated user from JWT or legacy token

    Returns:
        Trade record details
    """
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    agent_id = user["sub"]
    store = TradeStore(db)

    # Get all trades for this opportunity
    trades = await store.get_trades(opportunity_id=trade_id)

    if not trades:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Verify ownership
    trade = trades[0]
    if trade.get("agent_name") != agent_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this trade")

    return trade


@router.post("", dependencies=[Depends(check_kill_switch)])
@audit_event("trades.create")
async def create_trade(
    payload: dict,
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Create a new trade record.

    Args:
        payload: Trade data (opportunity_id, order_result, risk_evaluation)
        user: Authenticated user from JWT or legacy token

    Returns:
        Success message
    """
    db = getattr(request.app.state, "db", None)
    if not db:
        raise HTTPException(status_code=500, detail="Database not available")

    agent_id = user["sub"]
    store = TradeStore(db)

    # Extract fields from payload
    opportunity_id = payload.get("opportunity_id")
    order_result = payload.get("order_result")
    risk_evaluation = payload.get("risk_evaluation")

    if not opportunity_id or not order_result:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: opportunity_id, order_result",
        )

    # Save the trade
    await store.save_trade(
        opportunity_id=opportunity_id,
        order_result=order_result,
        risk_evaluation=risk_evaluation,
        agent_name=agent_id,
    )

    return {"status": "ok", "message": "Trade created"}
