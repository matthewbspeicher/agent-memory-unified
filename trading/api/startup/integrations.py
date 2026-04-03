"""Integration startup for prediction markets and external data sources."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config import Config
    from data.bus import DataBus
    
logger = logging.getLogger(__name__)


async def setup_kalshi(
    config: Config,
    data_bus: DataBus,
) -> tuple[Any, Any]:
    """
    Initialize Kalshi prediction markets integration.
    
    Returns:
        (kalshi_source, kalshi_client) or (None, None) if not configured
    """
    if not config.kalshi_key_id or not config.kalshi_private_key_path:
        if config.kalshi_key_id or config.kalshi_private_key_path:
            logger.warning(
                "Kalshi integration disabled due to incomplete config: key_id=%s private_key_path=%s",
                bool(config.kalshi_key_id),
                bool(config.kalshi_private_key_path),
            )
        return None, None
    
    try:
        from adapters.kalshi.client import KalshiClient
        from adapters.kalshi.data_source import KalshiDataSource

        _kalshi_client = KalshiClient(
            key_id=config.kalshi_key_id,
            private_key_path=config.kalshi_private_key_path,
            demo=config.kalshi_demo,
        )
        _kalshi_source = KalshiDataSource(_kalshi_client)
        # Attach to DataBus so Kalshi agents can access it
        data_bus._kalshi_source = _kalshi_source
        logger.info(
            "Kalshi integration enabled (%s)",
            "demo" if config.kalshi_demo else "LIVE",
        )
        return _kalshi_source, _kalshi_client
    except Exception as exc:
        logger.warning("Kalshi setup failed (continuing without it): %s", exc)
        return None, None


async def setup_polymarket(
    config: Config,
    data_bus: DataBus,
    all_brokers: dict,
) -> tuple[Any, Any]:
    """
    Initialize Polymarket prediction markets integration.
    
    Returns:
        (polymarket_source, polymarket_broker) or (None, None) if not configured
    """
    if not config.polymarket_private_key:
        return None, None
    
    try:
        from adapters.polymarket.client import PolymarketClient
        from adapters.polymarket.broker import PolymarketBroker
        from adapters.polymarket.data_source import PolymarketDataSource

        _poly_client = PolymarketClient(
            private_key=config.polymarket_private_key,
            funder=config.polymarket_funder or "",
            api_key=config.polymarket_api_key,
            signature_type=config.polymarket_signature_type,
            creds_path=config.polymarket_creds_path,
            rpc_url=config.polymarket_rpc_url,
            dry_run=config.polymarket_dry_run,
            relayer_api_key=config.polymarket_relayer_api_key,
            relayer_address=config.polymarket_relayer_address,
        )
        _polymarket_source = PolymarketDataSource(_poly_client)
        polymarket_broker = PolymarketBroker(
            _poly_client,
            data_source=_polymarket_source,
            creds_path=config.polymarket_creds_path,
            dry_run=config.polymarket_dry_run,
        )
        await polymarket_broker.connection.connect()
        data_bus._polymarket_source = _polymarket_source
        
        # Add to brokers map
        all_brokers["polymarket"] = polymarket_broker
        
        logger.info(
            "Polymarket integration enabled (%s)",
            "dry-run" if config.polymarket_dry_run else "LIVE",
        )
        return _polymarket_source, polymarket_broker
    except Exception as exc:
        logger.warning("Polymarket setup failed (continuing without it): %s", exc)
        return None, None


async def setup_bittensor(
    config: Config,
    db: Any,
    data_bus: DataBus,
    event_bus: Any,
    signal_bus: Any,
) -> tuple[bool, dict[str, Any]]:
    """
    Initialize Bittensor Subnet 8 (Taoshi PTN) integration.
    
    Returns:
        (enabled, components_dict) where components_dict contains:
        - store, source, adapter, scheduler, evaluator
    """
    if not config.bittensor_enabled:
        return False, {}
    
    try:
        from storage.bittensor import BittensorStore
        from data.bittensor_source import BittensorDataSource
        from integrations.bittensor.adapter import TaoshiProtocolAdapter
        from integrations.bittensor.scheduler import TaoshiScheduler
        from integrations.bittensor.evaluator import BittensorEvaluator
        from integrations.bittensor.models import RankingConfig

        _bt_store = BittensorStore(db)
        _bt_source = BittensorDataSource(_bt_store)
        data_bus._bittensor_source = _bt_source

        _bt_adapter = TaoshiProtocolAdapter(
            network=config.bittensor_network,
            endpoint=config.bittensor_endpoint,
            wallet_name=config.bittensor_wallet_name,
            hotkey_path=config.bittensor_hotkey_path,
            hotkey=config.bittensor_hotkey,
            subnet_uid=config.bittensor_subnet_uid,
        )
        await _bt_adapter.connect()
        
        _bt_healthy = await _bt_adapter.smoke_test()
        
        if not _bt_healthy:
            logger.warning("Bittensor smoke test failed — integration disabled")
            return False, {}
        
        _bt_scheduler = TaoshiScheduler(
            adapter=_bt_adapter,
            store=_bt_store,
            event_bus=event_bus,
            signal_bus=signal_bus,
            selection_policy=config.bittensor_selection_policy,
            selection_metric=config.bittensor_selection_metric,
            top_miners=config.bittensor_top_miners,
            derivation_version=config.bittensor_derivation_version,
        )
        
        _coingecko_client = None
        if config.coingecko_api_key:
            from data.coingecko import CoinGeckoClient
            _coingecko_client = CoinGeckoClient(api_key=config.coingecko_api_key)
            logger.info("CoinGecko client created for Bittensor evaluator")
        
        _bt_evaluator = BittensorEvaluator(
            store=_bt_store,
            data_bus=data_bus,
            event_bus=event_bus,
            delay_factor=config.bittensor_evaluation_delay_factor,
            scoring_version=config.bittensor_scoring_version,
            coingecko=_coingecko_client,
            adapter=_bt_adapter,
            ranking_config=RankingConfig(
                min_windows_for_ranking=config.bittensor_min_windows_for_ranking,
                alpha_decay_per_window=config.bittensor_hybrid_alpha_decay_per_window,
                alpha_floor=config.bittensor_hybrid_alpha_floor,
                lookback_windows=config.bittensor_ranking_lookback_windows,
            ),
        )
        
        missing_runtime_parts: list[str] = []
        if not getattr(_bt_scheduler, "supports_collection", True):
            missing_runtime_parts.append("collection")
        if not getattr(_bt_evaluator, "supports_evaluation", True):
            missing_runtime_parts.append("evaluation")
        
        if missing_runtime_parts:
            logger.warning(
                "Bittensor transport is healthy, but runtime %s is not implemented; "
                "integration remains disabled",
                " and ".join(missing_runtime_parts),
            )
            return False, {}
        
        logger.info(
            "Bittensor integration enabled (network=%s, subnet=%d)",
            config.bittensor_network,
            config.bittensor_subnet_uid,
        )
        
        return True, {
            "store": _bt_store,
            "source": _bt_source,
            "adapter": _bt_adapter,
            "scheduler": _bt_scheduler,
            "evaluator": _bt_evaluator,
            "ranking_config": {
                "min_windows_for_ranking": config.bittensor_min_windows_for_ranking,
                "alpha_decay_per_window": config.bittensor_hybrid_alpha_decay_per_window,
                "alpha_floor": config.bittensor_hybrid_alpha_floor,
                "lookback_windows": config.bittensor_ranking_lookback_windows,
            }
        }
    except Exception as exc:
        logger.warning("Bittensor setup failed (continuing without it): %s", exc)
        return False, {}
