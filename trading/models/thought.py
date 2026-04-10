from sqlmodel import SQLModel, Field  # type: ignore[import-untyped]
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Column
from datetime import datetime
import uuid
from enum import Enum
from typing import List, Dict, Any


class ActionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class ThoughtRecord(SQLModel, table=True):
    __tablename__ = "thought_records"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    timestamp: datetime
    agent_name: str = Field(index=True)
    symbol: str
    action: ActionType
    conviction_score: float
    rule_evaluations: List[Dict[str, Any]] = Field(default=[], sa_column=Column(JSONB))
    memory_context: List[str] = Field(default=[], sa_column=Column(JSONB))
