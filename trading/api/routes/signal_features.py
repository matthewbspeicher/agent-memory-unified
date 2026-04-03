"""Signal-time feature store API routes."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.auth import verify_api_key
from storage.signal_features import SignalFeatureStore

router = APIRouter(prefix="/analytics/signal-features", tags=["signal-features"])

logger = logging.getLogger(__name__)


def _get_store(request: Request) -> SignalFeatureStore:
    return SignalFeatureStore(request.app.state.db)


@router.get("/{opportunity_id}")
async def get_signal_features(
    request: Request,
    opportunity_id: str,
    _: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Return the canonical signal-time feature row for a single opportunity."""
    store = _get_store(request)
    row = await store.get(opportunity_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No signal features for opportunity {opportunity_id!r}")
    return row


@router.get("")
async def list_signal_features(
    request: Request,
    agent_name: str | None = Query(None, description="Filter by agent name"),
    symbol: str | None = Query(None, description="Filter by symbol ticker"),
    signal: str | None = Query(None, description="Filter by signal name"),
    start: str | None = Query(None, description="ISO timestamp lower bound on opportunity_timestamp"),
    end: str | None = Query(None, description="ISO timestamp upper bound on opportunity_timestamp"),
    limit: int = Query(100, ge=1, le=1000),
    _: str = Depends(verify_api_key),
) -> list[dict[str, Any]]:
    """Return filtered signal-time feature rows.

    All query parameters are optional. Results are ordered by opportunity_timestamp DESC.
    """
    store = _get_store(request)
    return await store.list_filtered(
        agent_name=agent_name,
        symbol=symbol,
        signal=signal,
        start=start,
        end=end,
        limit=limit,
    )


@router.post("/backfill")
async def backfill_signal_features(
    request: Request,
    agent_name: str | None = Query(None, description="Restrict backfill to this agent"),
    limit: int = Query(50, ge=1, le=500, description="Max opportunities to backfill"),
    _: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Admin trigger for best-effort backfill of historical opportunities.

    Backfilled rows use capture_status='synthetic_backfill' and feature_version='1.0-backfill'
    to distinguish them from live-captured rows.  Live rows are never overwritten by backfill.
    """
    from storage.opportunities import OpportunityStore

    db = request.app.state.db
    feature_store = SignalFeatureStore(db)
    opp_store = OpportunityStore(db)
    data_bus = getattr(request.app.state, "data_bus", None)

    if data_bus is None:
        raise HTTPException(status_code=503, detail="DataBus not available — cannot backfill")

    # Fetch raw opportunity dicts; reconstruct lightweight objects for capture
    opp_rows = await opp_store.list(agent_name=agent_name, limit=limit * 3)

    processed = 0
    skipped = 0
    failed = 0

    for row in opp_rows:
        if processed >= limit:
            break
        opp_id = str(row["id"])
        existing = await feature_store.get(opp_id)
        if existing and existing.get("capture_status") not in ("failed",):
            skipped += 1
            continue
        try:
            # Build a minimal Opportunity-like object from the DB row for capture
            _opp = _row_to_opportunity(row)
            if _opp is None:
                skipped += 1
                continue
            from learning.signal_features import SignalFeatureCapture
            capture = SignalFeatureCapture(store=feature_store, data_bus=data_bus)
            await capture.capture(_opp)
            # Mark synthetic rows clearly
            await feature_store.upsert(
                opp_id,
                capture_status="synthetic_backfill",
                feature_version="1.0-backfill",
            )
            processed += 1
        except Exception as exc:
            logger.warning("Backfill failed for opportunity %s: %s", opp_id, exc)
            failed += 1

    return {
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "note": "Backfilled rows use capture_status='synthetic_backfill'. Live rows were not overwritten.",
    }


def _row_to_opportunity(row: dict[str, Any]) -> Any:
    """Reconstruct a minimal Opportunity from a DB row for backfill purposes."""
    import json as _json
    from datetime import datetime, timezone
    from agents.models import Opportunity, OpportunityStatus
    from broker.models import Symbol, AssetType

    try:
        ticker = row["symbol"]
        data: dict = {}
        if row.get("data"):
            try:
                data = _json.loads(row["data"])
            except Exception:
                pass
        raw_asset_type = data.get("asset_type") or row.get("asset_type")
        broker_id = row.get("broker_id") or data.get("broker_id")
        try:
            asset_type = AssetType(raw_asset_type) if raw_asset_type else None
        except ValueError:
            asset_type = None
        if asset_type is None and broker_id in {"kalshi", "kalshi_paper", "polymarket", "polymarket_paper"}:
            asset_type = AssetType.PREDICTION
        sym = Symbol(ticker=ticker, asset_type=asset_type or AssetType.STOCK)
        ts_str = row.get("created_at", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if not ts.tzinfo:
                ts = ts.replace(tzinfo=timezone.utc)
        except Exception:
            ts = datetime.now(timezone.utc)
        return Opportunity(
            id=row["id"],
            agent_name=row["agent_name"],
            symbol=sym,
            signal=row["signal"],
            confidence=float(row.get("confidence", 0.5)),
            reasoning=row.get("reasoning", ""),
            data=data,
            timestamp=ts,
            status=OpportunityStatus(row.get("status", "pending")),
            broker_id=broker_id,
        )
    except Exception:
        return None
