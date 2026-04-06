"""
Configuration management - explicit Config dataclass + load_config()

Replaces pydantic-settings with a simpler, more testable approach.
"""
import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_origin, get_args, Union


@dataclass
class Config:
    """Application configuration with sensible defaults"""

    # IBKR connection
    ib_host: str = "127.0.0.1"
    ib_port: int | None = None
    ib_client_id: int = 1
    ib_readonly: bool = False

    # Node Role
    worker_mode: bool = False
    oracle_url: str | None = None

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_key: str = ""

    # Reconnection
    reconnect_max_delay: int = 60
    reconnect_initial_delay: int = 5

    # Storage
    db_path: str = "data.db"
    database_url: str | None = None
    database_ssl: bool = True
    database_ssl_verify: bool = True
    broker_mode: str = "paper"
    slack_webhook_url: str | None = None
    slack_signing_secret: str | None = None
    consensus_threshold: int = 1
    consensus_window_minutes: int = 15
    import_dir: str = "data/imports"

    # WhatsApp
    whatsapp_phone_id: str | None = None
    whatsapp_token: str | None = None
    whatsapp_verify_token: str | None = None
    whatsapp_app_secret: str | None = None
    whatsapp_allowed_numbers: str | None = None

    # LLM
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"

    # AWS Bedrock LLM
    bedrock_region: str | None = None
    bedrock_access_key_id: str | None = None
    bedrock_secret_access_key: str | None = None
    bedrock_model: str = "anthropic.claude-3-haiku-20240307-v1:0"

    llm_fallback_chain: list[str] = field(
        default_factory=lambda: ["anthropic", "bedrock", "groq", "ollama", "rule-based"]
    )

    # Kalshi prediction markets
    kalshi_key_id: str | None = None
    kalshi_private_key_path: str | None = None
    kalshi_demo: bool = True

    # Polymarket prediction markets
    polymarket_private_key: str | None = None
    polymarket_funder: str | None = None
    polymarket_api_key: str | None = None
    polymarket_relayer_api_key: str | None = None
    polymarket_relayer_address: str | None = None
    polymarket_dry_run: bool = True
    polymarket_rpc_url: str = "https://polygon-rpc.com"
    polymarket_signature_type: int = 0
    polymarket_creds_path: str = "data/polymarket_creds.json"
    polymarket_ws_enabled: bool = True
    polymarket_ws_reconnect_max_secs: int = 30
    arb_spread_retention_days: int = 7

    # Supabase observability
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_key: str | None = None

    # Remembr.dev Arena integration
    remembr_agent_token: str | None = None
    remembr_base_url: str = "https://remembr.dev/api/v1"
    remembr_timeout: int = 5
    remembr_owner_token: str | None = None

    # remembr.dev Memory API
    remembr_api_key: str | None = None
    remembr_shared_api_key: str | None = None

    # Hardware acceleration
    gpu_enabled: bool = False

    # Journal Vector Index
    journal_index_enabled: bool = False
    journal_index_model: str = "all-MiniLM-L6-v2"
    journal_index_path: str = "data/journal_index"
    journal_index_space: str = "cosine"
    journal_index_ef_construction: int = 200
    journal_index_m: int = 16
    journal_index_ef_search: int = 50
    journal_index_max_elements: int = 100_000
    journal_index_persist_interval: int = 300

    # Trade Journal LLM
    journal_llm_provider: str = "anthropic"
    journal_llm_api_key: str | None = None
    journal_llm_model: str = "claude-haiku-4-5"
    journal_llm_base_url: str | None = None

    # Morning Brief
    brief_cron: str = "30 8 * * 1-5"

    # Order confirmation
    order_timeout: int = 10

    # External Data Services
    metaculus_token: str | None = None
    manifold_markets_key: str | None = None
    newsapi_key: str | None = None
    news_feeds: list[str] = field(default_factory=list)
    news_poll_interval: int = 90
    alpha_vantage_key: str | None = None
    coingecko_api_key: str | None = None
    massive_key: str | None = None
    tradercongress_api_key: str | None = None
    tradier_token: str | None = None
    tradier_account_id: str | None = None
    tradier_sandbox: bool = True

    # Alpaca
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_paper: bool = True
    alpaca_data_feed: str = "iex"

    alpaca_streaming: bool = False
    tradier_streaming: bool = False

    # Multi-broker routing
    primary_broker: str | None = None
    broker_routing: dict[str, str] = field(default_factory=dict)

    # Distributed Intelligence
    redis_url: str = "redis://localhost:6379/0"

    quiverquant_api_key: str | None = None

    # Bittensor Subnet 8
    bittensor_enabled: bool = False
    bittensor_network: str = "finney"
    bittensor_endpoint: str = "ws://localhost:9944"
    bittensor_wallet_name: str = "sta_wallet"
    bittensor_hotkey_path: str = ""
    bittensor_hotkey: str = "sta_hotkey"
    bittensor_subnet_uid: int = 8
    bittensor_selection_policy: str = "all"
    bittensor_selection_metric: str = "incentive"
    bittensor_top_miners: int = 10
    bittensor_min_responses_for_consensus: int = 1
    bittensor_min_responses_for_opportunity: int = 3
    bittensor_evaluation_delay_factor: float = 1.2
    bittensor_min_windows_for_ranking: int = 20
    bittensor_rolling_window: int = 500
    bittensor_hybrid_alpha_initial: float = 1.0
    bittensor_hybrid_alpha_decay_per_window: float = 0.003
    bittensor_derivation_version: str = "v1"
    bittensor_scoring_version: str = "v1"
    bittensor_hybrid_alpha_floor: float = 0.1
    bittensor_ranking_lookback_windows: int = 500
    bittensor_mock: bool = False

    # Sovereign Arbitrageur & Capital Governor
    enable_arbitrage: bool = False
    arb_slippage_threshold_bps: int = 5
    arb_toxicity_threshold: float = 0.7
    arb_timeout_secs: int = 2

    # Hermes Autonomy
    hermes_full_autonomy: bool = False

    governor_max_drawdown_pct: float = 5.0
    governor_min_sharpe_promotion: float = 1.5
    governor_cache_ttl_secs: int = 300
    governor_base_allocation: float = 100.0

    # Paper Trading
    paper_trading: bool = True
    paper_trading_initial_balance: float = 10000.0
    agents_config: str | None = None

    # Backtesting
    backtest_min_sharpe: float = 1.0
    backtest_min_trades: int = 50
    backtest_default_hold_bars: int = 10
    backtest_slippage_pct: float = 0.001
    backtest_fee_per_trade: float = 1.00


_KNOWN_BROKERS = {"ibkr", "alpaca", "tradier", "kalshi", "polymarket"}


def _parse_value(value: str, field_type: type) -> Any:
    """Parse environment variable string into typed value"""
    # Handle generic types (list[str], dict[str, str], etc.)
    origin = get_origin(field_type)
    if origin is not None:
        if origin is list:
            # Comma-separated list
            return [v.strip() for v in value.split(",") if v.strip()]
        elif origin is dict:
            # JSON-encoded dict
            return json.loads(value)

    # Handle basic types
    if field_type == bool:
        return value.lower() in ("true", "1", "yes")
    elif field_type == int:
        return int(value)
    elif field_type == float:
        return float(value)
    elif field_type == list:
        # Comma-separated list (untyped)
        return [v.strip() for v in value.split(",") if v.strip()]
    elif field_type == dict:
        # JSON-encoded dict (untyped)
        return json.loads(value)
    else:
        return value


def _load_dotenv(env_file: str) -> dict[str, str]:
    """Load .env file into a dictionary"""
    env_vars = {}
    if not Path(env_file).exists():
        return env_vars

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    return env_vars


def load_config(env_file: str = ".env") -> Config:
    """
    Load configuration from environment variables and .env file

    Priority: OS environment variables > .env file > defaults

    Args:
        env_file: Path to .env file (default: .env)

    Returns:
        Configured Config instance

    Raises:
        ValueError: If validation fails (e.g., invalid broker, live mode without API key)
    """
    # Load .env file
    dotenv_vars = _load_dotenv(env_file)

    # Merge with OS environment (OS env takes priority)
    all_env = {**dotenv_vars, **os.environ}

    # Extract STA_ prefixed vars
    config_dict = {}
    for key, value in all_env.items():
        if key.startswith("STA_"):
            field_name = key[4:].lower()  # Remove STA_ prefix
            config_dict[field_name] = value

    if "REDIS_PRIVATE_URL" in all_env and "redis_url" not in config_dict:
        config_dict["redis_url"] = all_env["REDIS_PRIVATE_URL"]
    elif "REDIS_URL" in all_env and "redis_url" not in config_dict:
        config_dict["redis_url"] = all_env["REDIS_URL"]

    # Parse typed values
    config = Config()
    annotations = Config.__annotations__  # Get annotations from class, not instance

    for field_name, raw_value in config_dict.items():
        if not hasattr(config, field_name):
            continue  # Ignore unknown fields

        # Get field type from annotation
        field_type = annotations.get(field_name)
        if field_type is None:
            continue

        # Handle Optional[T] types (T | None)
        origin = get_origin(field_type)
        if origin is Union:  # This is a Union type
            args = get_args(field_type)
            # Extract non-None type
            field_type = args[0] if args[0] is not type(None) else args[1]

        # Parse and set value
        try:
            parsed_value = _parse_value(raw_value, field_type)
            setattr(config, field_name, parsed_value)
        except (ValueError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid value for {field_name}: {raw_value}") from e

    # Post-processing validations
    _validate_brokers(config)
    _apply_ib_port_default(config)
    _check_live_mode_api_key(config)

    return config


def _validate_brokers(config: Config) -> None:
    """Validate broker names"""
    if config.primary_broker and config.primary_broker not in _KNOWN_BROKERS:
        raise ValueError(
            f"Unknown primary_broker: '{config.primary_broker}'. "
            f"Known: {sorted(_KNOWN_BROKERS)}"
        )

    for asset_type, broker in config.broker_routing.items():
        if broker not in _KNOWN_BROKERS:
            raise ValueError(
                f"Unknown broker '{broker}' in broker_routing[{asset_type}]. "
                f"Known: {sorted(_KNOWN_BROKERS)}"
            )


def _apply_ib_port_default(config: Config) -> None:
    """Apply IB port default based on broker_mode"""
    if config.ib_port is None:
        config.ib_port = 4002 if config.broker_mode == "paper" else 4001


def _check_live_mode_api_key(config: Config) -> None:
    """Check API key requirements for live mode"""
    if config.broker_mode == "live" and not config.api_key:
        raise ValueError("STA_API_KEY must be set in live mode")

    if config.broker_mode == "paper" and not config.api_key:
        warnings.warn(
            "Running in paper mode without STA_API_KEY — API is unauthenticated",
            UserWarning,
            stacklevel=3,
        )
