from sqlmodel import SQLModel, Field
from enum import Enum
import uuid
from datetime import datetime
from typing import Optional


class PlatformTier(str, Enum):
    EXPLORER = "explorer"
    TRADER = "trader"
    ENTERPRISE = "enterprise"
    WHALE = "whale"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    tier: PlatformTier = Field(default=PlatformTier.EXPLORER)
    stripe_customer_id: Optional[str] = Field(default=None, unique=True)
    stripe_subscription_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
