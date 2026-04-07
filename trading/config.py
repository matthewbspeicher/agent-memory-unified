"""
Configuration management - explicit Config pydantic models + load_config()
"""

from __future__ import annotations
import json
import os
import warnings
from pydantic import BaseModel, Field, field_validator, model_validator
from pathlib import Path
from typing import Any

from intelligence.config import IntelligenceConfig


class BrokerConfig(BaseModel):
    ib_host: str = "127.0.0.1"
    ib_port: int = 4002
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
        if v and v not in ["ibkr", "alpaca", "tradier", "paper", "kalshi", "polymarket"]:
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
    ollama_base_url: str = "http://localhost:11434"
    bedrock_region: str | None = None
    bedrock_access_key_id: str | None = None
    bedrock_secret_access_key: str | None = None
    bedrock_model: str = "anthropic.claude-3-haiku-20240307-v1:0"
    fallback_chain: list[str] = Field(
        default_factory=lambda: ["anthropic", "bedrock", "groq", "ollama", "rule-based"]
    )


class Config(BaseModel):
    """Application configuration with strict Pydantic validation."""

    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    bittensor: BittensorConfig = Field(default_factory=BittensorConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    intel: IntelligenceConfig = Field(default_factory=IntelligenceConfig)

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

    # --- Backward Compatibility Properties ---
    @property
    def bittensor_enabled(self) -> bool: return self.bittensor.enabled
    @property
    def bittensor_network(self) -> str: return self.bittensor.network
    @property
    def bittensor_subnet_uid(self) -> int: return self.bittensor.subnet_uid
    @property
    def bittensor_mock(self) -> bool: return self.bittensor.mock
    @property
    def ib_port(self) -> int: return self.broker.ib_port
    @property
    def primary_broker(self) -> str | None: return self.broker.primary_broker
    @property
    def tradier_token(self) -> str | None: return self.broker.tradier_token
    @property
    def tradier_account_id(self) -> str | None: return self.broker.tradier_account_id
    @property
    def broker_routing(self) -> dict[str, str]: return self.broker.routing
    
    def __getattr__(self, name: str):
        # Delegate to sub-configs if not found
        for section in ["broker", "bittensor", "llm", "intel"]:
            obj = getattr(self, section)
            if hasattr(obj, name):
                return getattr(obj, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


def load_config(env_file: str = ".env") -> Config:
    """
    Load configuration from environment variables and .env file.
    Uses Pydantic for validation and type conversion.
    """
    from dotenv import load_dotenv
    load_dotenv(env_file)

    # Load from environment variables
    env_data = {}
    for key, value in os.environ.items():
        if key.startswith("STA_"):
            field_name = key[4:].lower()
            env_data[field_name] = value

    # Special handling for nested configs if provided in ENV
    processed_data = {}
    for k, v in env_data.items():
        if k == "primary_broker":
            if "broker" not in processed_data: processed_data["broker"] = {}
            processed_data["broker"]["primary_broker"] = v
            continue
        if k == "tradier_token":
            if "broker" not in processed_data: processed_data["broker"] = {}
            processed_data["broker"]["tradier_token"] = v
            continue
        if k == "tradier_account_id":
            if "broker" not in processed_data: processed_data["broker"] = {}
            processed_data["broker"]["tradier_account_id"] = v
            continue
        if k == "broker_routing":
            if "broker" not in processed_data: processed_data["broker"] = {}
            processed_data["broker"]["routing"] = v
            continue

        if "_" in k:
            # Check for known prefixes
            found = False
            for prefix in ["broker", "bittensor", "llm", "intel"]:
                if k.startswith(f"{prefix}_"):
                    rest = k[len(prefix)+1:]
                    if prefix not in processed_data: processed_data[prefix] = {}
                    processed_data[prefix][rest] = v
                    found = True
                    break
            if not found:
                processed_data[k] = v
        else:
            processed_data[k] = v

    # Handle JSON string for broker.routing (mapped from broker_routing or sta_broker_routing)
    if "broker" in processed_data and "routing" in processed_data["broker"]:
        if isinstance(processed_data["broker"]["routing"], str):
            try:
                processed_data["broker"]["routing"] = json.loads(processed_data["broker"]["routing"])
            except json.JSONDecodeError:
                pass

    try:
        return Config.model_validate(processed_data)
    except Exception as e:
        # Backward compatibility for tests expecting ValueError
        msg = str(e)
        if "Unknown" in msg or "primary_broker" in msg or "routing" in msg:
            raise ValueError(msg)
        raise
