"""
Configuration management - explicit Config pydantic models + load_config()
"""

from __future__ import annotations
import json
import os
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any, ClassVar

from intelligence.config import IntelligenceConfig


_KNOWN_BROKERS = {"ibkr", "alpaca", "tradier", "paper"}


class BrokerConfig(BaseModel):
    ib_host: str = "127.0.0.1"
    ib_port: int | None = None
    ib_client_id: int = 1
    ib_readonly: bool = False
    mode: str = "paper"
    primary_broker: str | None = None
    routing: dict[str, str] = Field(default_factory=dict)

    tradier_token: str | None = None
    tradier_account_id: str | None = None
    tradier_sandbox: bool = True
    tradier_streaming: bool = False

    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_paper: bool = True
    alpaca_data_feed: str = "iex"
    alpaca_streaming: bool = False

    @field_validator("primary_broker")
    @classmethod
    def validate_primary_broker(cls, v):
        if v and v not in [
            "ibkr",
            "alpaca",
            "tradier",
            "paper",
            "kalshi",
            "polymarket",
        ]:
            raise ValueError(f"Unknown primary broker: {v}")
        return v

    @field_validator("routing")
    @classmethod
    def validate_routing(cls, v):
        valid = ["ibkr", "alpaca", "tradier", "paper", "kalshi", "polymarket"]
        for asset, broker in v.items():
            if broker not in valid:
                raise ValueError(f"Unknown routing broker for {asset}: {broker}")
        return v


class BittensorConfig(BaseModel):
    """Bittensor Subnet 8 (Vanta Network) configuration."""

    enabled: bool = False
    network: str = "finney"
    endpoint: str = "ws://localhost:9944"
    wallet_name: str = "sta_wallet"
    hotkey_path: str = ""
    hotkey: str = "sta_hotkey"
    subnet_uid: int = 8
    selection_policy: str = "all"
    selection_metric: str = "incentive"
    top_miners: int = 10
    min_responses_for_consensus: int = 1
    min_responses_for_opportunity: int = 3
    evaluation_delay_factor: float = 1.2
    min_windows_for_ranking: int = 20
    rolling_window: int = 500
    hybrid_alpha_initial: float = 1.0
    hybrid_alpha_decay_per_window: float = 0.003
    derivation_version: str = "v1"
    scoring_version: str = "v1"
    hybrid_alpha_floor: float = 0.1
    ranking_lookback_windows: int = 500
    streams: list[str] = Field(default_factory=lambda: ["BTCUSD-5m"])
    direct_query_enabled: bool = False
    mock: bool = False


class LLMConfig(BaseModel):
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    bedrock_region: str | None = None
    bedrock_access_key_id: str | None = None
    bedrock_secret_access_key: str | None = None
    bedrock_model: str = "anthropic.claude-3-haiku-20240307-v1:0"
    fallback_chain: list[str] = Field(
        default_factory=lambda: ["anthropic", "bedrock", "groq", "ollama", "rule-based"]
    )

    # Cost control
    daily_budget_cents: int = 500  # $5.00/day
    warning_threshold_pct: float = 0.80  # Alert at 80%
    grace_period_minutes: int = 15  # After ceiling hit
    cost_table_override: str | None = None  # JSON override
    agent_budgets: dict[str, int] = Field(
        default_factory=dict
    )  # per-agent daily cap (cents)


class CompetitionConfig(BaseModel):
    """Arena competition system configuration."""

    enabled: bool = True
    initial_elo: int = 1000
    elo_decay_enabled: bool = True
    funding_arb_enabled: bool = False
    hmm_regime_enabled: bool = False
    meta_learner_enabled: bool = False
    lunarcrush_enabled: bool = False


class Config(BaseModel):
    """Application configuration with strict Pydantic validation."""

    model_config = {"extra": "allow"}

    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    bittensor: BittensorConfig = Field(default_factory=BittensorConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    intel: IntelligenceConfig = Field(default_factory=IntelligenceConfig)
    competition: CompetitionConfig = Field(default_factory=CompetitionConfig)

    # Flat accessors for nested config — backward compat with code that does config.ib_host
    _NESTED_PREFIXES: ClassVar[dict[str, str]] = {
        "broker": "broker",
        "bittensor": "bittensor",
        "llm": "llm",
        "intel": "intel",
        "competition": "competition",
    }
    _BROKER_FIELDS: ClassVar[set[str]] = {
        "ib_host",
        "ib_port",
        "ib_client_id",
        "ib_readonly",
        "mode",
        "primary_broker",
        "routing",
        "tradier_token",
        "tradier_account_id",
        "tradier_sandbox",
        "tradier_streaming",
        "alpaca_api_key",
        "alpaca_secret_key",
        "alpaca_paper",
        "alpaca_data_feed",
        "alpaca_streaming",
    }

    def __getattr__(self, name: str) -> Any:
        # Try direct access first, then nested delegation.
        try:
            return object.__getattribute__(self, name)
        except AttributeError:
            pass
        # Check Pydantic extra fields (model_config extra="allow")
        try:
            extra = object.__getattribute__(self, "__pydantic_extra__")
            if extra is not None and name in extra:
                return extra[name]
        except AttributeError:
            pass
        # Access class attributes via type(self) to avoid recursion
        cls = type(self)
        # Try broker fields first (most common flat access pattern)
        if name in cls._BROKER_FIELDS:
            return getattr(object.__getattribute__(self, "broker"), name)
        # Try nested configs by prefix (e.g. bittensor_enabled -> bittensor.enabled)
        for prefix, attr in cls._NESTED_PREFIXES.items():
            if name.startswith(prefix + "_"):
                suffix = name[len(prefix) + 1 :]
                nested = object.__getattribute__(self, attr)
                if hasattr(nested, suffix):
                    return getattr(nested, suffix)
        raise AttributeError(f"'Config' object has no attribute {name!r}")

    # Missing flat fields for compatibility
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    ollama_base_url: str | None = None
    bedrock_region: str | None = None
    bedrock_model: str | None = None
    bedrock_access_key_id: str | None = None
    bedrock_secret_access_key: str | None = None
    remembr_owner_token: str | None = None
    remembr_agent_token: str | None = None
    remembr_base_url: str = "https://remembr.dev/api/v1"
    remembr_timeout: int | None = None
    remembr_api_key: str | None = None
    remembr_shared_api_key: str | None = None
    paper_trading: bool | None = None
    paper_trading_initial_balance: float = 100000.0
    massive_key: str | None = None
    news_feeds: list[str] | None = None
    news_poll_interval: int | None = None
    alpaca_streaming: bool | None = None
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_data_feed: str | None = None
    tradier_streaming: bool | None = None
    tradier_token: str | None = None
    tradier_sandbox: bool | None = None
    journal_index_enabled: bool = False
    journal_index_persist_interval: int | None = None
    journal_index_model: str = "all-MiniLM-L6-v2"
    journal_index_path: str = "data/journal_index"
    journal_index_space: str = "cosine"
    journal_index_ef_construction: int = 200
    journal_index_m: int = 16
    journal_index_ef_search: int = 50
    journal_index_max_elements: int = 100_000
    gpu_enabled: bool | None = None
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_key: str | None = None
    kalshi_demo: bool | None = None
    polymarket_private_key: str | None = None
    polymarket_funder: str | None = None
    polymarket_api_key: str | None = None
    polymarket_signature_type: int | None = None
    polymarket_creds_path: str | None = None
    polymarket_rpc_url: str | None = None
    polymarket_dry_run: bool | None = None
    polymarket_relayer_api_key: str | None = None
    polymarket_relayer_address: str | None = None
    # External API keys (not nested under a prefix)
    metaculus_token: str | None = None
    manifold_markets_key: str | None = None
    newsapi_key: str | None = None
    alpha_vantage_key: str | None = None
    coingecko_api_key: str | None = None
    tradercongress_api_key: str | None = None
    quiverquant_api_key: str | None = None

    agents_config: str | None = None
    redis_url: str | None = None
    broker_routing: dict[str, str] | None = None
    arb_toxicity_threshold: float | None = None
    order_timeout: int | None = None
    knowledge_graph_enabled: bool = False
    rate_limit_enabled: bool = False

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

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
    slack_webhook_url: str | None = None
    discord_webhook_url: str | None = None
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

    # Kalshi prediction markets
    kalshi_key_id: str | None = None
    kalshi_private_key_path: str | None = None
    kalshi_private_key_b64: str | None = None  # base64-encoded PEM; preferred over path on Railway
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

    # Local Memory Store (fallback when remembr.dev unavailable)
    local_memory_enabled: bool = False
    local_memory_db_path: str = "data/memory.db"

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
    news_feeds: list[str] = Field(default_factory=list)
    news_poll_interval: int = 90
    alpha_vantage_key: str | None = None
    coingecko_api_key: str | None = None
    massive_key: str | None = None
    tradercongress_api_key: str | None = None

    # Distributed Intelligence
    redis_url: str = "redis://localhost:6379/0"

    quiverquant_api_key: str | None = None

    # Sovereign Arbitrageur & Capital Governor
    enable_arbitrage: bool = False
    arb_slippage_threshold_bps: int = 5
    arb_toxicity_threshold: float = 0.7
    arb_timeout_secs: int = 2
    arb_auto_execute: bool = False
    arb_min_profit_bps: float = 5.0
    arb_max_position_usd: float = 100.0
    portfolio_max_position_usd: float = 0.0

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

    # BitGet crypto exchange
    bitget_api_key: str | None = None
    bitget_secret_key: str | None = None
    bitget_passphrase: str | None = None


def load_config(env_file: str = ".env") -> Any:
    """
    Load configuration from environment variables and .env file.
    Uses Pydantic for validation and type conversion.
    """
    from dotenv import load_dotenv

    # Load from environment variables first to preserve them.
    # Order matters: capture the real env (Railway/cloud) before .env can
    # leak into os.environ, then load .env without override so cloud vars
    # always win. STA_DATABASE_URL is the production DB source of truth.
    actual_env = os.environ.copy()
    load_dotenv(env_file, override=False)
    env_data: dict[str, Any] = {}
    for key, value in os.environ.items():
        if key.startswith("STA_"):
            field_name = key[4:].lower()
            env_data[field_name] = value

    # Explicitly override with original environment variables (Railway/Cloud)
    for key, value in actual_env.items():
        if key.startswith("STA_"):
            field_name = key[4:].lower()
            env_data[field_name] = value

    # Also accept standard env vars for Railway/cloud compatibility
    # Prioritize original environment variables
    db_url = actual_env.get("DATABASE_URL") or os.environ.get("DATABASE_URL")
    if db_url and "database_url" not in env_data:
        # Only use DATABASE_URL if it's not pointing to localhost (not reachable on Railway)
        if "localhost" not in db_url and "127.0.0.1" not in db_url:
            env_data["database_url"] = db_url

    redis_url = actual_env.get("REDIS_URL") or os.environ.get("REDIS_URL")
    if redis_url and "redis_url" not in env_data:
        env_data["redis_url"] = redis_url

    # Fields that should remain flat (not split into nested config)
    _flat_fields = set(Config.model_fields.keys())

    # Parse JSON strings for list/dict fields
    _list_fields = {"news_feeds", "bittensor_streams"}
    _dict_fields = {"broker_routing"}
    for k in list(env_data.keys()):
        if k in _list_fields and isinstance(env_data[k], str):
            try:
                env_data[k] = json.loads(env_data[k])
            except (json.JSONDecodeError, ValueError):
                env_data[k] = [s.strip() for s in env_data[k].split(",") if s.strip()]
        elif k in _dict_fields and isinstance(env_data[k], str):
            try:
                env_data[k] = json.loads(env_data[k])
            except (json.JSONDecodeError, ValueError):
                pass

    # Special handling for nested configs if provided in ENV
    # (e.g. STA_BROKER_MODE -> config.broker.mode)
    # But only split into nested if the flat field doesn't exist on Config
    processed_data: dict[str, Any] = {}
    for k, v in env_data.items():
        # Always populate flat fields first
        if k in _flat_fields:
            processed_data[k] = v
        if "_" in k:
            prefix, rest = k.split("_", 1)
            if prefix in ["broker", "bittensor", "llm", "intel", "competition"]:
                if prefix not in processed_data or not isinstance(
                    processed_data.get(prefix), dict
                ):
                    processed_data.setdefault(prefix, {})
                if isinstance(processed_data.get(prefix), dict):
                    processed_data[prefix][rest] = v
            elif k not in _flat_fields:
                processed_data[k] = v
        elif k not in _flat_fields:
            processed_data[k] = v

    # LLM fallback chain: parse from nested or flat
    llm_nested = processed_data.get("llm", {})
    if isinstance(llm_nested, dict) and "fallback_chain" in llm_nested:
        val = llm_nested["fallback_chain"]
        if isinstance(val, str):
            try:
                llm_nested["fallback_chain"] = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                llm_nested["fallback_chain"] = [
                    s.strip() for s in val.split(",") if s.strip()
                ]
    if isinstance(llm_nested, dict) and "agent_budgets" in llm_nested:
        val = llm_nested["agent_budgets"]
        if isinstance(val, str):
            try:
                llm_nested["agent_budgets"] = json.loads(val)
            except (json.JSONDecodeError, ValueError):
                llm_nested["agent_budgets"] = {}

    # Special handling for Railway PORT and standard HOST env vars
    if "PORT" in os.environ:
        processed_data["api_port"] = int(os.environ["PORT"])
    if "HOST" in os.environ:
        processed_data["api_host"] = os.environ["HOST"]

    config = Config.model_validate(processed_data)

    # Validate broker names
    if config.primary_broker and config.primary_broker not in _KNOWN_BROKERS:
        raise ValueError(
            f"Unknown primary_broker '{config.primary_broker}'. "
            f"Valid brokers: {sorted(_KNOWN_BROKERS)}"
        )
    if config.broker_routing:
        for asset_class, broker_name in config.broker_routing.items():
            if broker_name not in _KNOWN_BROKERS:
                raise ValueError(
                    f"Unknown broker '{broker_name}' in broker_routing['{asset_class}']. "
                    f"Valid brokers: {sorted(_KNOWN_BROKERS)}"
                )

    return config
