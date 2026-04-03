"""Market regime detection API routes."""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Market Regime"], dependencies=[Depends(verify_api_key)])


@router.get("/regime")
async def get_current_regime(request: Request, symbol: str = "SPY", period: str = "3mo"):
    """
    Detect the current market regime for a given equity symbol plus prediction
    market liquidity overview for Kalshi and Polymarket.

    Response shape:
      {
        "equity": { regime, adx, volatility_pct, sma_slope, bars_analyzed, detected_at },
        "prediction_markets": {
          "kalshi":     { regime, avg_spread_cents, avg_volume_24h },
          "polymarket": { regime, avg_spread_cents, avg_volume_24h }
        }
      }

    Uses ADX, annualized volatility, and SMA slope to classify the equity regime.
    The prediction_markets section is best-effort; missing sources return UNKNOWN.
    """
    data_bus = getattr(request.app.state, "data_bus", None)
    if not data_bus:
        raise HTTPException(status_code=501, detail="DataBus not available")

    try:
        from broker.models import Symbol as Sym, AssetType
        from regime.detector import RegimeDetector

        sym = Sym(ticker=symbol.upper(), asset_type=AssetType.STOCK)
        bars = await data_bus.get_historical(sym, timeframe="1d", period=period)

        if not bars:
            raise HTTPException(
                status_code=404,
                detail=f"No historical data available for {symbol}",
            )

        detector = RegimeDetector()
        snapshot = detector.detect_with_snapshot(bars)
        equity_data = snapshot.to_dict()

        # Prediction market liquidity overview (best-effort)
        liquidity_detector = getattr(request.app.state, "liquidity_detector", None)
        prediction_markets: dict = {}

        if liquidity_detector:
            for broker_id in ("kalshi", "polymarket"):
                liq = await liquidity_detector.detect_platform(broker_id)
                prediction_markets[broker_id] = {
                    "regime": liq.regime.value,
                    "avg_spread_cents": liq.spread_cents,
                    "avg_volume_24h": liq.volume_24h,
                }
        else:
            from regime.models import LiquidityRegime
            for broker_id in ("kalshi", "polymarket"):
                prediction_markets[broker_id] = {
                    "regime": LiquidityRegime.UNKNOWN.value,
                    "avg_spread_cents": 0.0,
                    "avg_volume_24h": 0.0,
                }

        return {
            "equity": equity_data,
            "prediction_markets": prediction_markets,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Regime detection failed for %s", symbol)
        raise HTTPException(status_code=500, detail="Regime detection failed")


@router.get("/regime/filter/{agent_name}")
async def check_agent_regime_filter(agent_name: str, request: Request, symbol: str = "SPY"):
    """
    Check whether the given agent is allowed to trade in the current market regime.
    """
    data_bus = getattr(request.app.state, "data_bus", None)
    regime_filter = getattr(request.app.state, "regime_filter", None)

    if not regime_filter:
        raise HTTPException(status_code=501, detail="Regime filter not configured")

    if not data_bus:
        raise HTTPException(status_code=501, detail="DataBus not available")

    try:
        from broker.models import Symbol as Sym, AssetType
        from regime.detector import RegimeDetector
        from regime.models import MarketRegime

        sym = Sym(ticker=symbol.upper(), asset_type=AssetType.STOCK)
        bars = await data_bus.get_historical(sym, timeframe="1d", period="3mo")

        if not bars:
            # No data → unknown regime → allow
            return {
                "agent_name": agent_name,
                "regime": MarketRegime.UNKNOWN.value,
                "is_allowed": True,
                "reason": "No market data available — defaulting to allow",
            }

        detector = RegimeDetector()
        snapshot = detector.detect_with_snapshot(bars)
        regime = snapshot.regime
        allowed = regime_filter.is_allowed(agent_name, regime)

        return {
            "agent_name": agent_name,
            "regime": regime.value,
            "is_allowed": allowed,
            "allowed_regimes": [r.value for r in regime_filter.get_allowed_regimes(agent_name)],
            "adx": snapshot.adx,
            "volatility_pct": snapshot.volatility_pct,
        }

    except HTTPException:
        raise
    except Exception:
        logger.exception("Regime filter check failed for %s", agent_name)
        raise HTTPException(status_code=500, detail="Regime filter check failed")
