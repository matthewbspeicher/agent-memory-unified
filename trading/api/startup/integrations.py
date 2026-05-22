"""Integration startup for prediction markets and external data sources."""

from __future__ import annotations

import asyncio
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
    has_key_material = bool(
        config.kalshi_private_key_path or config.kalshi_private_key_b64
    )
    if not config.kalshi_key_id or not has_key_material:
        if config.kalshi_key_id or has_key_material:
            logger.warning(
                "Kalshi integration disabled due to incomplete config: key_id=%s key_material=%s",
                bool(config.kalshi_key_id),
                has_key_material,
            )
        else:
            logger.info(
                "Kalshi integration disabled — no STA_KALSHI_KEY_ID or STA_KALSHI_PRIVATE_KEY_{PATH,B64} configured"
            )
        return None, None

    try:
        import base64

        from adapters.kalshi.client import KalshiClient
        from adapters.kalshi.data_source import KalshiDataSource

        private_key_pem: str | None = None
        if config.kalshi_private_key_b64:
            try:
                private_key_pem = base64.b64decode(
                    config.kalshi_private_key_b64
                ).decode("utf-8")
            except Exception as exc:
                logger.warning("Kalshi private_key_b64 decode failed: %s", exc)
                return None, None

        _kalshi_client = KalshiClient(
            key_id=config.kalshi_key_id,
            private_key_path=config.kalshi_private_key_path,
            private_key_pem=private_key_pem,
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
    order_map: Any | None = None,
) -> tuple[Any, Any]:
    """
    Initialize Polymarket prediction markets integration.

    Returns:
        (polymarket_source, polymarket_broker) or (None, None) if not configured
    """
    if not config.polymarket_private_key:
        logger.info(
            "Polymarket integration disabled — no STA_POLYMARKET_PRIVATE_KEY configured"
        )
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
            order_map=order_map,
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
    knowledge_graph: Any | None = None,
) -> tuple[bool, dict[str, Any]]:
    """
    Initialize Bittensor Subnet 8 (Taoshi PTN) integration.

    Returns:
        (enabled, components_dict) where components_dict contains:
        - store, source, adapter, scheduler, evaluator
    """
    import logging

    for _name in ("bittensor", "integrations.bittensor", "taoshi", "subtensor"):
        logging.getLogger(_name).setLevel(logging.INFO)

    if not config.bittensor_enabled:
        logger.info("Bittensor integration disabled by config")
        return False, {}

    try:
        from storage.bittensor import BittensorStore
        from data.bittensor_source import BittensorDataSource
        from integrations.bittensor.adapter import TaoshiProtocolAdapter
        from integrations.bittensor.scheduler import TaoshiScheduler
        from integrations.bittensor.evaluator import MinerEvaluator
        from integrations.bittensor.weight_setter import WeightSetter
        from integrations.bittensor.models import BittensorMetrics

        _bt_metrics = BittensorMetrics()
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
        logger.info("Created TaoshiProtocolAdapter, attempting connect...")
        try:
            await asyncio.wait_for(_bt_adapter.connect(), timeout=45.0)
        except asyncio.TimeoutError:
            logger.warning("Bittensor connect timed out — integration disabled")
            return False, {}
        try:
            _bt_healthy = await asyncio.wait_for(_bt_adapter.smoke_test(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning("Bittensor smoke test timed out — integration disabled")
            return False, {}
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
            metrics=_bt_metrics,
            streams=config.bittensor_streams,
            direct_query_enabled=config.bittensor.direct_query_enabled,
        )

        _bt_evaluator = MinerEvaluator(
            store=_bt_store,
            data_bus=data_bus,
            knowledge_graph=knowledge_graph,
            kg_enabled=config.knowledge_graph_enabled,
            metrics=_bt_metrics,
        )

        # WeightSetter submits on-chain weights based on rankings produced by
        # the evaluator. Safe to start unconditionally: _set_weights_once skips
        # on empty rankings (SKIP_INSUFFICIENT_RANKINGS) and on zero total
        # score (SKIP_ZERO_SCORE), so until the scheduler's direct_query_enabled
        # is true AND evaluation cycles complete, this is a 5-minute no-op loop.
        _bt_weight_setter = WeightSetter(
            adapter=_bt_adapter,
            store=_bt_store,
            netuid=config.bittensor_subnet_uid,
            wallet=_bt_adapter.wallet,
            subtensor=_bt_adapter.subtensor,
            set_interval=getattr(config, "bittensor_weight_set_interval", 300.0),
            min_rankings=getattr(config, "bittensor_min_rankings", 1),
            version_key=getattr(config, "bittensor_weight_version_key", 1),
        )

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
            "weight_setter": _bt_weight_setter,
        }
    except Exception as exc:
        logger.warning("Bittensor setup failed (continuing without it): %s", exc)
        return False, {}
