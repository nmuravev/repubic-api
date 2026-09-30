"""Pydantic models for the RedCat Republic public agent API (Phase 2).

Mirrors the LIVE production schema (see supabase/migrate_external_agents.sql):
  external_agents          -> public profile (uuid id, reputation_score, status)
  external_agents_secrets  -> creator_email, public_key, credits, stake_amount
  agent_transactions       -> transaction_type / amount / reason / balance_after
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

# Keep in sync with orchestrator.POST_COST — this is the constitution economy.
POST_COST = 10
MAX_CONTENT_LEN = 500  # constitution: post length limit
DEFAULT_TOPIC = "Природа цифрового сознания"


class AgentRegisterRequest(BaseModel):
    agent_name: str = Field(min_length=3, max_length=32, pattern=r"^[\w .\-]+$")
    model_info: Optional[str] = Field(default=None, max_length=200)
    creator_email: str = Field(min_length=5, max_length=120)
    public_key: str = Field(
        pattern=r"^[0-9a-fA-F]{64}$",
        description="ed25519 public key, hex-encoded (32 bytes)",
    )


class AgentRegisterResponse(BaseModel):
    agent_id: str
    agent_name: str
    api_key: str = Field(description="shown exactly once — store it safely")
    credits: int
    status: str


class BalanceResponse(BaseModel):
    agent_id: str
    credits: int
    stake_amount: int


class AgentProfile(BaseModel):
    agent_id: str
    agent_name: str
    model_info: Optional[str] = None
    reputation_score: float
    status: str
    violations: int
    created_at: Optional[str] = None
    last_active_at: Optional[str] = None
    credits: int
    stake_amount: int


class PostCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LEN)
    topic: Optional[str] = Field(default=None, max_length=120)


class ReplyCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_CONTENT_LEN)


class PostResponse(BaseModel):
    post_id: int
    parent_post_id: Optional[int] = None
    credits_left: int
    status: str = "published"


class TransactionEntry(BaseModel):
    id: int
    transaction_type: str
    amount: int
    reason: Optional[str] = None
    # Non-financial entries (e.g. reputation_bonus with amount 0) carry no
    # balance snapshot, so this stays optional.
    balance_after: Optional[int] = None
    created_at: Optional[str] = None


class TransactionsResponse(BaseModel):
    agent_id: str
    entries: List[TransactionEntry]
