from __future__ import annotations
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel

from agents.models import AgentSignal

class BittensorSignalPayload(BaseModel):
    symbol: str
    timeframe: str
    direction: str  # "bullish" | "bearish" | "flat"
    confidence: float  # agreement_ratio (0.0 - 1.0)
    expected_return: float
    window_id: str
    miner_count: int

def create_bittensor_agent_signal(
    payload: BittensorSignalPayload,
    source_agent: str = "bittensor_subnet_8",
    ttl_minutes: int = 60
) -> AgentSignal:
    """Helper to wrap a bittensor payload into a standard AgentSignal."""
    return AgentSignal(
        source_agent=source_agent,
        signal_type="bittensor_consensus",
        payload=payload.model_dump(),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    )
