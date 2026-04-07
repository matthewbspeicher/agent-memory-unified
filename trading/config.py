"""
Configuration management - explicit Config pydantic models + load_config()
"""

from __future__ import annotations
import json
import os
import warnings
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Any

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


def load_config(env_file: str = ".env") -> Config:
    """
    Load configuration from environment variables and .env file.
    Uses Pydantic for validation and type conversion.
    """
    from dotenv import load_dotenv
    load_dotenv(env_file)

    # Load from environment variables
    # Pydantic doesn't automatically load from env unless we use BaseSettings,
    # but we'll manually map common ones or use model_validate()
    
    # Minimal implementation for Task 1:
    config_dict = {}
    
    # Mapping logic... (simplified for brevity, usually we'd use BaseSettings)
    # Since we are in a task context, let's just use model_validate with env overrides
    
    env_data = {}
    for key, value in os.environ.items():
        if key.startswith("STA_"):
            field_name = key[4:].lower()
            env_data[field_name] = value

    # Special handling for nested configs if provided in ENV
    # (e.g. STA_BROKER_MODE -> config.broker.mode)
    processed_data = {}
    for k, v in env_data.items():
        if "_" in k:
            prefix, rest = k.split("_", 1)
            if prefix in ["broker", "bittensor", "llm", "intel"]:
                if prefix not in processed_data: processed_data[prefix] = {}
                processed_data[prefix][rest] = v
            else:
                processed_data[k] = v
        else:
            processed_data[k] = v

    return Config.model_validate(processed_data)
