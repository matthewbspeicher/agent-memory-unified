from __future__ import annotations

import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from api.auth import verify_api_key
from api.dependencies import get_db

router = APIRouter(prefix="/api/v1/tax", tags=["tax"])


@router.get("/export")
async def export_tax_report(
    year: int = Query(default_factory=lambda: datetime.now().year - 1),
    agent_name: str | None = Query(None),
    db=Depends(get_db),
    _: str = Depends(verify_api_key),
):
    """Export Form 8949-compatible tax report CSV for the specified year."""
    from storage.trade_csv import TaxExporter

    exporter = TaxExporter(db)
    output_path = f"/tmp/tax_report_{year}_{datetime.now().strftime('%H%M%S')}.csv"

    try:
        await exporter.export_tax_report(
            year=year,
            agent_name=agent_name,
            output_path=output_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Tax export failed: {exc}")

    if not os.path.exists(output_path):
        raise HTTPException(
            status_code=404, detail="No trades found for the specified period"
        )

    return FileResponse(
        path=output_path,
        media_type="text/csv",
        filename=f"tax_report_{year}.csv",
    )
