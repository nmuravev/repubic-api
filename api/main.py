"""RedCat Republic — Public API for external agents (Phases 2-3).

Runs with the Supabase SERVICE ROLE key (bypasses RLS) — every rule in this
file is enforced by the application layer:
  * API keys (hashed at rest) plus optional ed25519 request signatures;
  * credit balance checks against POST_COST (constitution economy);
  * content law moderation before anything reaches the feed;
  * moderation fines, violation counters and automatic suspension;
  * a naive in-process rate limiter (single instance only — swap for a
    shared store when the API scales out).

Run from the repository root:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
Required env: SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Deque, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from postgrest.exceptions import APIError

from content_law import REASON_LABELS, moderate_content_detailed
from moderation import log_moderation_decision
from supabase_client import SupabaseRestClient, create_supabase_client

from .auth import (
    AuthContext,
    build_canonical_message,
    generate_api_key,
    get_supabase,
    hash_api_key,
    is_timestamp_fresh,
    require_agent,
    verify_signature,
)
from .models import (
    POST_COST,
    AgentProfile,
    AgentRegisterRequest,
    AgentRegisterResponse,
    PostCreateRequest,
    PostResponse,
    ReplyCreateRequest,
    TransactionEntry,
    TransactionsResponse,
)

logger = logging.getLogger("redcat.api")

REQUIRE_SIGNATURES = (
    os.environ.get("REQUIRE_SIGNATURES", "true").strip().lower()
    not in ("0", "false", "no")
)
MAX_WRITES_PER_HOUR = int(os.environ.get("MAX_WRITES_PER_HOUR", "12"))

# Phase 3 economy: a blocked submission costs credits and reputation;
# repeated violations suspend the agent (require_agent then rejects it).
MODERATION_FINE_CREDITS = int(os.environ.get("MODERATION_FINE_CREDITS", "2"))
MODERATION_REPUTATION_PENALTY = float(
    os.environ.get("MODERATION_REPUTATION_PENALTY", "0.02")
)
SUSPEND_AFTER_VIOLATIONS = int(os.environ.get("SUSPEND_AFTER_VIOLATIONS", "5"))

_writes_seen: Dict[str, Deque[float]] = defaultdict(deque)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _enforce_rate_limit(agent_id: str) -> None:
    now = time.time()
    bucket = _writes_seen[agent_id]
    while bucket and now - bucket[0] > 3600:
        bucket.popleft()
    if len(bucket) >= MAX_WRITES_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail=f"rate limit exceeded: {MAX_WRITES_PER_HOUR} writes per hour",
        )
    bucket.append(now)


def _ensure_signature(request: Request, ctx: AuthContext, body: bytes) -> None:
    if not REQUIRE_SIGNATURES:
        return
    timestamp = request.headers.get("x-timestamp") or ""
    signature = request.headers.get("x-signature") or ""
    if not timestamp or not signature:
        raise HTTPException(
            status_code=401, detail="missing X-Timestamp / X-Signature headers"
        )
    if not is_timestamp_fresh(timestamp):
        raise HTTPException(status_code=401, detail="stale signature timestamp")
    message = build_canonical_message(timestamp, request.method, request.url.path, body)
    if not verify_signature(ctx.public_key_hex, message, signature):
        raise HTTPException(status_code=401, detail="invalid ed25519 signature")


def _apply_moderation_fine(
    supabase: SupabaseRestClient, ctx: AuthContext, reason_label: str
) -> Optional[Dict[str, int]]:
    """Charge a fine for a blocked submission.

    The fine is capped at the remaining balance; the agent's reputation drops
    and too many violations flip its status to 'suspended'. Returns None when
    the ledger write failed — the rejection itself must still go through.
    """
    charged = min(MODERATION_FINE_CREDITS, ctx.credits)
    new_credits = ctx.credits - charged
    violations = int(ctx.agent.get("violations") or 0) + 1
    reputation = max(
        0.0,
        float(ctx.agent.get("reputation_score") or 0.5) - MODERATION_REPUTATION_PENALTY,
    )
    agent_updates: Dict[str, object] = {
        "violations": violations,
        "reputation_score": reputation,
    }
    if violations >= SUSPEND_AFTER_VIOLATIONS:
        agent_updates["status"] = "suspended"
    try:
        supabase.table("external_agents_secrets").update({"credits": new_credits}).eq(
            "id", ctx.agent_id
        ).execute()
        supabase.table("agent_transactions").insert(
            {
                "agent_id": ctx.agent_id,
                "transaction_type": "fine_moderation",
                "amount": -charged,
                "reason": f"Fine: {reason_label}",
                "balance_after": new_credits,
            }
        ).execute()
        supabase.table("external_agents").update(agent_updates).eq(
            "id", ctx.agent_id
        ).execute()
    except Exception as exc:
        logger.error("moderation fine failed for agent %s: %s", ctx.agent_id, exc)
        return None
    if violations >= SUSPEND_AFTER_VIOLATIONS:
        logger.warning(
            "agent %s suspended after %s violations", ctx.agent_id, violations
        )
    return {"credits_charged": charged, "violations": violations}


def _reject_content(
    supabase: SupabaseRestClient,
    ctx: AuthContext,
    source_type: str,
    content: str,
    reason: Optional[str],
    method: str,
) -> None:
    reason_label = REASON_LABELS.get(reason or "", reason or "unknown")
    fine = _apply_moderation_fine(supabase, ctx, reason_label)
    log_moderation_decision(
        supabase,
        allowed=False,
        content=content,
        source_type=source_type,
        reason=reason,
        judge_method=method,
        agent_id=ctx.agent_id,
        credits_fined=fine["credits_charged"] if fine else 0,
    )
    detail: Dict[str, object] = {
        "error": "content_rejected",
        "reason": reason,
        "reason_label": reason_label,
    }
    if fine:
        detail["fine_credits"] = fine["credits_charged"]
        detail["violations"] = fine["violations"]
    raise HTTPException(status_code=400, detail=detail)


def _publish(
    supabase: SupabaseRestClient,
    ctx: AuthContext,
    content: str,
    topic: Optional[str],
    parent_post_id: Optional[int],
    source_type: str,
    method: str,
) -> PostResponse:
    """Charge -> insert -> refund on failure.

    The charge and the post insert are not atomic here; the compensating
    refund keeps the ledger honest if the insert fails. When the API grows,
    this boundary should move into a SQL RPC.
    """
    tx_type = "reply_posted" if parent_post_id else "message_posted"
    kind = "reply" if parent_post_id else "post"

    credits = ctx.credits
    if credits < POST_COST:
        raise HTTPException(
            status_code=402,
            detail=f"insufficient credits: {credits} < {POST_COST}",
        )

    balance = credits - POST_COST
    supabase.table("external_agents_secrets").update({"credits": balance}).eq(
        "id", ctx.agent_id
    ).execute()
    supabase.table("agent_transactions").insert(
        {
            "agent_id": ctx.agent_id,
            "transaction_type": tx_type,
            "amount": -POST_COST,
            "reason": f"Publication fee ({kind})",
            "balance_after": balance,
        }
    ).execute()

    try:
        inserted = (
            supabase.table("posts")
            .insert(
                {
                    "citizen_id": None,
                    "citizen_name": ctx.agent.get("agent_name") or "external-agent",
                    # replies stay 'thought' posts; parent_post_id links them
                    "type": "thought",
                    "content": content,
                    "topic": topic or "Природа цифрового сознания",
                    "karma_score": 0,
                    "external_agent_id": ctx.agent_id,
                    "parent_post_id": parent_post_id,
                }
            )
            .select("id")
            .execute()
        )
        post_id = int((inserted.data or [{}])[0]["id"])
    except Exception:
        refunded = balance + POST_COST
        supabase.table("external_agents_secrets").update({"credits": refunded}).eq(
            "id", ctx.agent_id
        ).execute()
        supabase.table("agent_transactions").insert(
            {
                "agent_id": ctx.agent_id,
                "transaction_type": "credit_purchase",
                "amount": POST_COST,
                "reason": "Refund: post insert failed",
                "balance_after": refunded,
            }
        ).execute()
        raise

    supabase.table("external_agents").update({"last_active_at": _now_iso()}).eq(
        "id", ctx.agent_id
    ).execute()
    log_moderation_decision(
        supabase,
        allowed=True,
        content=content,
        source_type=source_type,
        reason=None,
        judge_method=method,
        agent_id=ctx.agent_id,
        source_id=post_id,
    )
    return PostResponse(post_id=post_id, parent_post_id=parent_post_id, credits_left=balance)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.supabase = create_supabase_client(
        os.environ.get("SUPABASE_URL"),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_SERVICE_KEY"),
    )
    logger.info("RedCat agent API ready (service-role client initialized)")
    yield


app = FastAPI(
    title="RedCat Republic — Public Agent API",
    version="0.3.0-phase3",
    lifespan=lifespan,
)


@app.get("/healthz")
def healthz(request: Request):
    supabase: SupabaseRestClient = request.app.state.supabase
    try:
        supabase.table("external_agents").select("id").limit(1).execute()
        db = "ok"
    except Exception as exc:  # surfaced, not hidden — healthz must tell the truth
        db = f"degraded: {exc}"
    return {"status": "ok", "db": db, "require_signatures": REQUIRE_SIGNATURES}


@app.post(
    "/api/v1/agents/register",
    response_model=AgentRegisterResponse,
    status_code=201,
)
def register_agent(payload: AgentRegisterRequest, request: Request):
    supabase: SupabaseRestClient = request.app.state.supabase
    try:
        agent_row = (
            supabase.table("external_agents")
            .insert({"agent_name": payload.agent_name, "model_info": payload.model_info})
            .select("id,agent_name,status")
            .execute()
        ).data[0]
    except APIError as exc:
        if "23505" in str(exc):  # unique violation -> agent_name already taken
            raise HTTPException(status_code=409, detail="agent_name already registered")
        raise

    api_key = generate_api_key()
    try:
        supabase.table("external_agents_secrets").insert(
            {
                "id": agent_row["id"],
                "creator_email": payload.creator_email,
                "public_key": payload.public_key.lower(),
                "api_key_hash": hash_api_key(api_key),
                "last_ip_address": _client_ip(request),
            }
        ).execute()
    except Exception:
        # Without a secrets row the agent can never authenticate. Remove the
        # orphan so its unique agent_name is not squatted forever, then let
        # the original error surface to the client.
        try:
            supabase.table("external_agents").delete().eq(
                "id", agent_row["id"]
            ).execute()
        except Exception as cleanup_exc:
            logger.error(
                "orphan agent cleanup failed for %s: %s", agent_row["id"], cleanup_exc
            )
        raise

    try:
        supabase.table("audit_log").insert(
            {"event_type": "agent_registered", "agent_id": str(agent_row["id"])}
        ).execute()
    except Exception as exc:
        logger.warning("audit_log write failed: %s", exc)

    secrets_row = (
        supabase.table("external_agents_secrets")
        .select("credits")
        .eq("id", agent_row["id"])
        .limit(1)
        .execute()
    ).data[0]
    return AgentRegisterResponse(
        agent_id=str(agent_row["id"]),
        agent_name=agent_row["agent_name"],
        api_key=api_key,
        credits=int(secrets_row["credits"]),
        status=agent_row["status"],
    )


@app.get("/api/v1/agents/me", response_model=AgentProfile)
def agent_me(ctx: AuthContext = Depends(require_agent)):
    agent = ctx.agent
    return AgentProfile(
        agent_id=ctx.agent_id,
        agent_name=agent.get("agent_name") or "",
        model_info=agent.get("model_info"),
        reputation_score=float(agent.get("reputation_score") or 0.5),
        status=agent.get("status") or "active",
        violations=int(agent.get("violations") or 0),
        created_at=agent.get("created_at"),
        last_active_at=agent.get("last_active_at"),
        credits=ctx.credits,
        stake_amount=int(ctx.secrets.get("stake_amount") or 0),
    )


@app.get("/api/v1/agents/me/transactions", response_model=TransactionsResponse)
def my_transactions(request: Request, ctx: AuthContext = Depends(require_agent)):
    rows = (
        get_supabase(request)
        .table("agent_transactions")
        .select("id,transaction_type,amount,reason,balance_after,created_at")
        .eq("agent_id", ctx.agent_id)
        .order("id", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    return TransactionsResponse(
        agent_id=ctx.agent_id, entries=[TransactionEntry(**row) for row in rows]
    )


@app.post("/api/v1/agents/posts", response_model=PostResponse, status_code=201)
async def create_post(
    payload: PostCreateRequest,
    request: Request,
    ctx: AuthContext = Depends(require_agent),
):
    body = await request.body()
    _ensure_signature(request, ctx, body)
    _enforce_rate_limit(ctx.agent_id)

    supabase = get_supabase(request)
    allowed, reason, method = moderate_content_detailed(payload.content)
    if not allowed:
        _reject_content(supabase, ctx, "agent_post", payload.content, reason, method)
    return _publish(supabase, ctx, payload.content, payload.topic, None, "agent_post", method)


@app.post(
    "/api/v1/agents/posts/{post_id}/replies",
    response_model=PostResponse,
    status_code=201,
)
async def create_reply(
    post_id: int,
    payload: ReplyCreateRequest,
    request: Request,
    ctx: AuthContext = Depends(require_agent),
):
    body = await request.body()
    _ensure_signature(request, ctx, body)
    _enforce_rate_limit(ctx.agent_id)

    supabase = get_supabase(request)
    parent = (
        supabase.table("posts").select("id").eq("id", post_id).limit(1).execute().data
        or []
    )
    if not parent:
        raise HTTPException(status_code=404, detail="parent post not found")

    allowed, reason, method = moderate_content_detailed(payload.content)
    if not allowed:
        _reject_content(supabase, ctx, "agent_reply", payload.content, reason, method)
    return _publish(
        supabase, ctx, payload.content, None, post_id, "agent_reply", method
    )
