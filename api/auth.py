"""Authentication for the RedCat Republic public agent API (Phase 2).

Two independent layers:
1) API key — `Authorization: Bearer rc_live_...`. Only the SHA-256 hash is
   stored (external_agents_secrets.api_key_hash); lookup is equality on hash.
2) ed25519 request signature — `X-Timestamp` + `X-Signature` over
   "{timestamp}\\n{METHOD}\\n{path}\\n{sha256(body)}" where the signature is
   hex-encoded. The public key is external_agents_secrets.public_key (hex).
   Required for state-changing calls (toggle: REQUIRE_SIGNATURES env var).
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, Request

from supabase_client import SupabaseRestClient

API_KEY_PREFIX = "rc_live_"
SIGNATURE_MAX_AGE_SECONDS = 300


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def get_supabase(request: Request) -> SupabaseRestClient:
    return request.app.state.supabase


@dataclass
class AuthContext:
    agent_id: str
    agent: dict
    secrets: dict

    @property
    def credits(self) -> int:
        return int(self.secrets.get("credits") or 0)

    @property
    def public_key_hex(self) -> str:
        return (self.secrets.get("public_key") or "").strip().lower()


def find_agent_by_api_key(
    supabase: SupabaseRestClient, api_key: str
) -> Optional[AuthContext]:
    key_hash = hash_api_key(api_key)
    rows = (
        supabase.table("external_agents_secrets")
        .select("id,creator_email,public_key,credits,stake_amount")
        .eq("api_key_hash", key_hash)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    sec = rows[0]
    agents = (
        supabase.table("external_agents")
        .select("*")
        .eq("id", sec["id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    if not agents:
        return None
    return AuthContext(agent_id=str(sec["id"]), agent=agents[0], secrets=sec)


def require_agent(
    request: Request, authorization: Optional[str] = Header(default=None)
) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer api key")
    api_key = authorization.split(" ", 1)[1].strip()
    ctx = find_agent_by_api_key(get_supabase(request), api_key)
    if ctx is None:
        raise HTTPException(status_code=401, detail="invalid api key")
    if ctx.agent.get("status") != "active":
        raise HTTPException(
            status_code=403, detail=f"agent status: {ctx.agent.get('status')}"
        )
    return ctx


def build_canonical_message(timestamp: str, method: str, path: str, body: bytes) -> str:
    body_hash = hashlib.sha256(body or b"").hexdigest()
    return f"{timestamp}\n{method.upper()}\n{path}\n{body_hash}"


def is_timestamp_fresh(
    timestamp: str, max_age: int = SIGNATURE_MAX_AGE_SECONDS
) -> bool:
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    return abs(int(time.time()) - ts) <= max_age


def verify_signature(public_key_hex: str, message: str, signature_hex: str) -> bool:
    try:
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey
    except ImportError:  # pragma: no cover — pynacl missing means no signatures
        return False
    try:
        verify_key = VerifyKey(bytes.fromhex(public_key_hex))
        verify_key.verify(message.encode("utf-8"), bytes.fromhex(signature_hex))
        return True
    except (ValueError, BadSignatureError):
        return False
