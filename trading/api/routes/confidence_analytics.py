"""Confidence calibration analytics API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from api.auth import verify_api_key
from learning.confidence_calibration import (
    ConfidenceCalibrationConfig,
    CalibrationRecommendation,
    assign_bucket,
    build_recommendation,
    classify_sample_quality,
)
from storage.confidence_calibration import ConfidenceCalibrationStore

router = APIRouter(prefix="/analytics/confidence", tags=["confidence-analytics"])

_DEFAULT_CFG = ConfidenceCalibrationConfig()


def _get_store(request: Request) -> ConfidenceCalibrationStore:
    return ConfidenceCalibrationStore(request.app.state.db)


@router.get("/strategies")
async def list_strategies_calibration(
    request: Request,
    window: str = Query("all", pattern="^(30d|90d|all)$"),
    _: str = Depends(verify_api_key),
):
    """Return calibration summaries across all strategies for the given window."""
    store = _get_store(request)
    rows = await store.list_all(window_label=window)
    return rows


@router.get("/{agent_name}")
async def get_strategy_calibration(
    request: Request,
    agent_name: str,
    window: str = Query("all", pattern="^(30d|90d|all)$"),
    _: str = Depends(verify_api_key),
):
    """Return all confidence bucket metrics for a single strategy."""
    store = _get_store(request)
    rows = await store.list_by_strategy(agent_name, window_label=window)
    return rows


@router.get("/{agent_name}/recommendation")
async def get_recommendation(
    request: Request,
    agent_name: str,
    confidence: float = Query(..., ge=0.0, le=1.0, description="Raw confidence score from the strategy"),
    window: str = Query("all", pattern="^(30d|90d|all)$"),
    _: str = Depends(verify_api_key),
):
    """Return sizing/filtering recommendation for a given strategy and confidence.

    Looks up the calibration summary for the matching bucket and window, then
    computes a multiplier and reject decision.
    """
    store = _get_store(request)

    # Build config from app state if available, otherwise use defaults
    cfg = _get_calibration_cfg(request)

    bucket = assign_bucket(confidence, cfg.bucket_width)

    # Look up stored calibration for this bucket
    cal_row = await store.get(agent_name, bucket, window)

    if cal_row is None:
        # No calibration data — return conservative fallback
        return {
            "agent_name": agent_name,
            "confidence": confidence,
            "bucket": bucket,
            "window": window,
            "sample_quality": "insufficient",
            "trade_count": 0,
            "expectancy": None,
            "multiplier": cfg.insufficient_sample_multiplier,
            "would_reject": False,
            "reason": f"No calibration data found for bucket {bucket} in window {window}; using conservative fallback.",
            "calibrated_score": None,
        }

    trade_count = cal_row["trade_count"]
    expectancy = float(cal_row["avg_net_return_pct"]) if cal_row.get("avg_net_return_pct") is not None else None

    rec = build_recommendation(
        bucket=bucket,
        trade_count=trade_count,
        expectancy=expectancy,
        avg_net_pnl=float(cal_row["avg_net_pnl"]) if cal_row.get("avg_net_pnl") is not None else None,
        cfg=cfg,
    )

    return {
        "agent_name": agent_name,
        "confidence": confidence,
        "bucket": rec.bucket,
        "window": window,
        "sample_quality": rec.sample_quality,
        "trade_count": rec.trade_count,
        "expectancy": rec.expectancy,
        "multiplier": rec.multiplier,
        "would_reject": rec.would_reject,
        "reason": rec.reason,
        "calibrated_score": rec.calibrated_score,
        "win_rate": cal_row.get("win_rate"),
        "profit_factor": cal_row.get("profit_factor"),
    }


def _get_calibration_cfg(request: Request) -> ConfidenceCalibrationConfig:
    """Extract ConfidenceCalibrationConfig from app state if available."""
    try:
        learning_cfg = getattr(request.app.state, "learning_config", None)
        if learning_cfg is not None and hasattr(learning_cfg, "confidence_calibration"):
            cal_cfg = learning_cfg.confidence_calibration
            return ConfidenceCalibrationConfig(
                enabled=cal_cfg.enabled,
                bucket_width=cal_cfg.bucket_width,
                min_trades_for_usable_bucket=cal_cfg.min_trades_for_usable_bucket,
                min_trades_for_hard_reject=cal_cfg.min_trades_for_hard_reject,
                insufficient_sample_multiplier=cal_cfg.insufficient_sample_multiplier,
                max_positive_multiplier=cal_cfg.max_positive_multiplier,
                max_composed_kelly_fraction=cal_cfg.max_composed_kelly_fraction,
                weak_expectancy_threshold=cal_cfg.weak_expectancy_threshold,
                moderate_expectancy_threshold=cal_cfg.moderate_expectancy_threshold,
                strong_expectancy_threshold=cal_cfg.strong_expectancy_threshold,
                allow_reject=cal_cfg.allow_reject,
            )
    except Exception:
        pass
    return _DEFAULT_CFG
