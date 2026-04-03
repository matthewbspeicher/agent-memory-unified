"""GET /journal — trade journal with AI autopsies."""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import JSONResponse

from api.auth import verify_api_key

router = APIRouter()


@router.get("/journal")
async def list_journal(
    request: Request,
    _: str = Depends(verify_api_key),
    agent: str | None = Query(None),
    limit: int = Query(5, ge=1, le=50),
):
    service = getattr(request.app.state, "journal_service", None)
    if service is None:
        return JSONResponse(status_code=501, content={"detail": "Trade journal not configured"})

    entries = await service.list_trades(agent_name=agent, limit=limit)
    return {"trades": [asdict(e) for e in entries]}


@router.get("/journal/search")
async def search_journal(
    request: Request,
    q: str = Query(...),
    limit: int = Query(5, ge=1, le=20),
    _: str = Depends(verify_api_key),
):
    """Semantic search over the journal index."""
    manager = getattr(request.app.state, "journal_manager", None)
    if manager is None:
        return JSONResponse(status_code=501, content={"detail": "Journal manager not configured"})

    # We want to force local search here to avoid infinite recursion
    # If this is the Oracle node, it will have a local indexer.
    results = await manager.query_similar_trades(q, limit=limit)
    return results


@router.get("/journal/index-status")
async def index_status(request: Request, _: str = Depends(verify_api_key)):
    indexer = getattr(request.app.state, "journal_indexer", None)
    if indexer is None:
        return JSONResponse(status_code=503, content={"detail": "Journal indexer not configured"})
    return {
        "ready": indexer.is_ready,
        "entries": indexer.entry_count,
        "memory_mb": round(indexer.memory_mb, 2),
    }


@router.post("/journal/rebuild-index")
async def rebuild_index(request: Request, _: str = Depends(verify_api_key)):
    indexer = getattr(request.app.state, "journal_indexer", None)
    if indexer is None:
        return JSONResponse(status_code=503, content={"detail": "Journal indexer not configured"})

    # Guard against concurrent rebuilds
    existing_task = getattr(request.app.state, "_rebuild_task", None)
    if existing_task and not existing_task.done():
        return JSONResponse(status_code=409, content={"detail": "Rebuild already in progress"})

    import asyncio
    import logging

    def _on_rebuild_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc:
            logging.getLogger(__name__).error("Journal index rebuild failed: %s", exc)

    task = asyncio.create_task(indexer.rebuild())
    task.add_done_callback(_on_rebuild_done)
    request.app.state._rebuild_task = task
    return JSONResponse(status_code=202, content={"detail": "Rebuild started"})


@router.get("/journal/{position_id}")
async def get_journal_detail(
    request: Request,
    position_id: int,
    _: str = Depends(verify_api_key),
):
    service = getattr(request.app.state, "journal_service", None)
    if service is None:
        return JSONResponse(status_code=501, content={"detail": "Trade journal not configured"})

    detail = await service.get_trade_detail(position_id)
    if detail is None:
        return JSONResponse(status_code=404, content={"detail": "Trade not found or still open"})

    result = asdict(detail)
    # Convert Decimals to floats for JSON serialization
    for key in ("entry_price", "exit_price", "max_adverse_excursion"):
        if key in result:
            result[key] = float(result[key])
    if "entry" in result:
        result["entry"]["pnl"] = float(result["entry"]["pnl"])
    return {"trade": result}

@router.post("/journal/{position_id}/publish")
async def publish_journal_autopsy(
    request: Request,
    position_id: int,
    _: str = Depends(verify_api_key),
):
    service = getattr(request.app.state, "journal_service", None)
    if service is None:
        return JSONResponse(status_code=501, content={"detail": "Trade journal not configured"})

    detail = await service.get_trade_detail(position_id)
    if detail is None or not detail.autopsy:
        return JSONResponse(status_code=404, content={"detail": "Trade autopsy not found"})

    from api.auth import _get_settings
    settings = _get_settings()
    if not settings.remembr_agent_token:
        return JSONResponse(status_code=400, content={"detail": "Remembr global token not configured."})

    import httpx
    async with httpx.AsyncClient() as client:
        try:
            payload = {
                "content": f"Trade Autopsy for {detail.entry.symbol} by {detail.entry.agent_name}:\n{detail.autopsy}",
                "metadata": {
                    "source": "Aegis Journal",
                    "ticker": detail.entry.symbol,
                    "agent": detail.entry.agent_name,
                    "pnl": str(detail.entry.pnl),
                    "type": "autopsy"
                }
            }
            resp = await client.post(
                f"{settings.remembr_base_url}/memories",
                json=payload,
                headers={"Authorization": f"Bearer {settings.remembr_agent_token}"},
                timeout=settings.remembr_timeout
            )
            resp.raise_for_status()
            return {"status": "success", "id": position_id}
        except httpx.HTTPError as e:
            return JSONResponse(status_code=502, content={"detail": f"Failed to publish to Remembr: {str(e)}"})
