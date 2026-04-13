"""
Configuration management - explicit Config pydantic models + load_config()
"""

from __future__ import annotations
import json
import os
from pydantic import BaseModel, Field
from typing import Any, ClassVar

from intelligence.config import IntelligenceConfig


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
    ollama_base_url: str = "http://localhost:11434"
    bedrock_region: str | None = None
    bedrock_access_key_id: str | None = None
    bedrock_secret_access_key: str | None = None
    bedrock_model: str = "anthropic.claude-3-haiku-20240307-v1:0"
    fallback_chain: list[str] = Field(
        default_factory=lambda: ["anthropic", "bedrock", "groq", "ollama", "rule-based"]
    )


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

    # Load from environment variables first to preserve them
    actual_env = os.environ.copy()

    # Load .env file (but don't override existing environment variables)
    load_dotenv(env_file, override=False)

    # Re-collect all relevant data, prioritizing actual environment variables
    env_data: dict[str, Any] = {}

    # Start with .env values (already in os.environ now, but we want to be explicit)
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

    # Special handling for Railway PORT and standard HOST env vars
    if "PORT" in os.environ:
        processed_data["api_port"] = int(os.environ["PORT"])
    if "HOST" in os.environ:
        processed_data["api_host"] = os.environ["HOST"]

    return Config.model_validate(processed_data)
