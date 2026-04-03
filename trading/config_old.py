from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # IBKR connection
    ib_host: str = "127.0.0.1"
    ib_port: int | None = None
    ib_client_id: int = 1
    ib_readonly: bool = False

    # Node Role
    worker_mode: bool = False  # STA_WORKER_MODE: skips execution setup
    oracle_url: str | None = None  # STA_ORACLE_URL: remote search fallback

    # API
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    api_key: str = ""

    # Reconnection
    reconnect_max_delay: int = 60
    reconnect_initial_delay: int = 5

    # Storage
    db_path: str = "data.db"
    database_url: str | None = (
        None  # postgresql://... from Supabase. If None, use SQLite.
    )
    database_ssl: bool = True
    database_ssl_verify: bool = (
        True  # set False only for Supabase pooler if cert verification fails
    )
    broker_mode: str = "paper"  # "live" or "paper"
    slack_webhook_url: str | None = None
    slack_signing_secret: str | None = None
    consensus_threshold: int = 1
    consensus_window_minutes: int = 15
    import_dir: str = "data/imports"  # watched by FidelityFileWatcher

    # WhatsApp
    whatsapp_phone_id: str | None = None
    whatsapp_token: str | None = None
    whatsapp_verify_token: str | None = None
    whatsapp_app_secret: str | None = None
    whatsapp_allowed_numbers: str | None = None  # comma-separated

    # LLM
    anthropic_api_key: str | None = None
    groq_api_key: str | None = None  # STA_GROQ_API_KEY — free tier: console.groq.com
    ollama_base_url: str = "http://localhost:11434"  # STA_OLLAMA_BASE_URL

    # AWS Bedrock LLM
    bedrock_region: str | None = None  # STA_BEDROCK_REGION (e.g., us-east-1)
    bedrock_access_key_id: str | None = None  # STA_BEDROCK_ACCESS_KEY_ID (optional if using IAM)
    bedrock_secret_access_key: str | None = None  # STA_BEDROCK_SECRET_ACCESS_KEY (optional if using IAM)
    bedrock_model: str = "anthropic.claude-3-haiku-20240307-v1:0"  # STA_BEDROCK_MODEL

    llm_fallback_chain: list[str] = [
        "anthropic",
        "bedrock",
        "groq",
        "ollama",
        "rule-based",
    ]  # STA_LLM_FALLBACK_CHAIN

    # Kalshi prediction markets
    kalshi_key_id: str | None = None
    kalshi_private_key_path: str | None = None
    kalshi_demo: bool = True  # True = demo.kalshi.co; set False for live trading

    # Polymarket prediction markets
    polymarket_private_key: str | None = None
    polymarket_funder: str | None = None
    polymarket_api_key: str | None = None
    polymarket_relayer_api_key: str | None = None
    polymarket_relayer_address: str | None = None
    polymarket_dry_run: bool = True
    polymarket_rpc_url: str = "https://polygon-rpc.com"
    polymarket_signature_type: int = 0  # 0=EOA (programmatic), 1=Magic/email
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
    remembr_timeout: int = 5  # seconds
    remembr_owner_token: str | None = (
        None  # STA_REMEMBRR_OWNER_TOKEN — used once for agent registration
    )

    # remembr.dev Memory API (separate from Arena leaderboard token)
    remembr_api_key: str | None = None  # STA_REMEMBRR_API_KEY
    remembr_shared_api_key: str | None = (
        None  # STA_REMEMBRR_SHARED_API_KEY — for market:observations namespace
    )

    # Hardware acceleration
    gpu_enabled: bool = False

    # Journal Vector Index (local HNSW acceleration)
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
    journal_llm_provider: str = "anthropic"  # "anthropic" | "openai_compatible"
    journal_llm_api_key: str | None = None  # falls back to anthropic_api_key
    journal_llm_model: str = "claude-haiku-4-5"
    journal_llm_base_url: str | None = None  # only for openai_compatible

    # Morning Brief
    brief_cron: str = "30 8 * * 1-5"  # 8:30 AM ET weekdays (1h before 9:30 open)

    # Order confirmation
    order_timeout: int = 10  # seconds to wait for IBKR order acknowledgment

    # External Data Services
    metaculus_token: str | None = None
    manifold_markets_key: str | None = None  # STA_MANIFOLD_MARKETS
    newsapi_key: str | None = None
    news_feeds: list[str] = []  # STA_NEWS_FEEDS — override default RSS feed list
    news_poll_interval: int = 90  # STA_NEWS_POLL_INTERVAL — seconds between poll cycles
    alpha_vantage_key: str | None = None
    coingecko_api_key: str | None = None
    massive_key: str | None = None
    tradercongress_api_key: str | None = None
    tradier_token: str | None = None
    tradier_account_id: str | None = None
    tradier_sandbox: bool = True  # True = sandbox.tradier.com

    # Alpaca
    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_paper: bool = True  # True = paper-api.alpaca.markets
    alpaca_data_feed: str = "iex"  # "iex" (free) | "sip" (paid, all exchanges)

    alpaca_streaming: bool = False  # opt-in for WebSocket quotes
    tradier_streaming: bool = False  # opt-in for SSE quotes

    # Multi-broker routing
    primary_broker: str | None = (
        None  # "ibkr" | "alpaca" | "tradier" — first connected if None
    )
    broker_routing: dict[
        str, str
    ] = {}  # e.g., {"STOCK": "alpaca", "OPTION": "tradier"}

    # Distributed Intelligence (Track 20)
    worker_mode: bool = False  # STA_WORKER_MODE: skips broker/execution init
    oracle_url: str | None = None  # STA_ORACLE_URL: remote node for search fallback
    redis_url: str = "redis://localhost:6379/0"  # STA_REDIS_URL: high-speed signal bus

    quiverquant_api_key: str | None = None

    # Bittensor Subnet 8 (Taoshi PTN)
    bittensor_enabled: bool = False
    bittensor_network: str = "finney"
    bittensor_endpoint: str = "ws://localhost:9944"
    bittensor_wallet_name: str = "sta_wallet"
    bittensor_hotkey_path: str = ""
    bittensor_hotkey: str = "sta_hotkey"
    bittensor_subnet_uid: int = 8
    bittensor_selection_policy: str = "all"  # "all" | "top_n" | "explicit"
    bittensor_selection_metric: str = "incentive"  # "incentive" | "vtrust" | "stake"
    bittensor_top_miners: int = 10  # only used when selection_policy="top_n"
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
    arb_slippage_threshold_bps: int = 5  # 5 basis points
    arb_toxicity_threshold: float = 0.7  # 0-1 scale
    arb_timeout_secs: int = 2

    # Hermes Autonomy
    hermes_full_autonomy: bool = False  # STA_HERMES_FULL_AUTONOMY: bypass APPROVE gates

    governor_max_drawdown_pct: float = 5.0
    governor_min_sharpe_promotion: float = 1.5
    governor_cache_ttl_secs: int = 300
    governor_base_allocation: float = 100.0  # Base size in USD

    # Paper Trading
    paper_trading: bool = True  # Default to paper mode for safety
    paper_trading_initial_balance: float = 10000.0  # Starting paper balance
    agents_config: str | None = None  # explicit path overrides paper_trading selection

    # Backtesting
    backtest_min_sharpe: float = 1.0
    backtest_min_trades: int = 50
    backtest_default_hold_bars: int = 10
    backtest_slippage_pct: float = 0.001
    backtest_fee_per_trade: float = 1.00

    _KNOWN_BROKERS = {"ibkr", "alpaca", "tradier", "kalshi", "polymarket"}

    @model_validator(mode="after")
    def validate_broker_names(self) -> "Settings":
        if self.primary_broker and self.primary_broker not in self._KNOWN_BROKERS:
            raise ValueError(
                f"Unknown primary_broker: '{self.primary_broker}'. "
                f"Known: {sorted(self._KNOWN_BROKERS)}"
            )
        for asset_type, broker in self.broker_routing.items():
            if broker not in self._KNOWN_BROKERS:
                raise ValueError(
                    f"Unknown broker '{broker}' in broker_routing[{asset_type}]. "
                    f"Known: {sorted(self._KNOWN_BROKERS)}"
                )
        return self

    @model_validator(mode="after")
    def apply_ib_port_default(self) -> "Settings":
        if self.ib_port is None:
            self.ib_port = 4002 if self.broker_mode == "paper" else 4001
        if self.broker_mode == "live" and not self.api_key:
            raise ValueError("STA_API_KEY must be set in live mode")
        if self.broker_mode == "paper" and not self.api_key:
            import warnings

            warnings.warn(
                "Running in paper mode without STA_API_KEY — API is unauthenticated",
                stacklevel=2,
            )
        return self

    model_config = {"env_file": ".env", "env_prefix": "STA_", "extra": "ignore"}
