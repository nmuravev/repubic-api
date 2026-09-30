"""End-to-end check of the public agent API against production Supabase.

Runs INSIDE GitHub Actions (workflow: api-e2e.yml) with the service-role key —
no hosted API server is needed: FastAPI's TestClient executes the app
in-process (lifespan included), so the whole flow stays within the
Supabase + GitHub stack.

Flow: register -> signed post -> rejected post (fine + violation) -> profile
-> ledger -> signed reply -> auth guards -> moderation log. Everything this
script creates is deleted in the finally block; the exit code is non-zero if
any check fails.

Usage (CI):
    SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... python validate_api_e2e.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List, Optional

from nacl.signing import SigningKey

SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").strip()
SERVICE_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
if not SUPABASE_URL or not SERVICE_KEY:
    print("❌ SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY must be set (CI secrets).")
    sys.exit(1)

from fastapi.testclient import TestClient  # noqa: E402

from api.auth import build_canonical_message  # noqa: E402
from api.main import app  # noqa: E402
from supabase_client import create_supabase_client  # noqa: E402

FAILURES: List[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok  {label}")
    else:
        FAILURES.append(label)
        print(f"  FAIL {label} -- {detail}")


def post_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def signed_headers(
    signing_key: SigningKey, api_key: str, method: str, path: str, body: bytes
) -> Dict[str, str]:
    timestamp = str(int(time.time()))
    message = build_canonical_message(timestamp, method, path, body)
    signature = signing_key.sign(message.encode("utf-8")).signature.hex()
    return {
        "Authorization": f"Bearer {api_key}",
        "X-Timestamp": timestamp,
        "X-Signature": signature,
        "Content-Type": "application/json",
    }


def cleanup(db, agent_id: Optional[str], post_ids: Optional[List[int]] = None) -> None:
    """Remove everything the E2E run created (verified at the end of the run)."""
    if not agent_id:
        return
    try:
        if post_ids is None:
            rows = (
                db.table("posts")
                .select("id")
                .eq("external_agent_id", agent_id)
                .execute()
                .data
                or []
            )
            post_ids = [r["id"] for r in rows]
        for pid in post_ids:
            try:
                db.table("votes").delete().eq("post_id", pid).execute()
            except Exception as exc:
                print(f"  note  votes cleanup for post {pid}: {exc}")
        db.table("posts").delete().eq("external_agent_id", agent_id).execute()
        db.table("agent_transactions").delete().eq("agent_id", agent_id).execute()
        db.table("moderation_log").delete().eq("agent_id", agent_id).execute()
        db.table("external_agents_secrets").delete().eq("id", agent_id).execute()
        try:
            db.table("audit_log").delete().eq("agent_id", agent_id).execute()
        except Exception as exc:
            print(f"  note  audit_log cleanup: {exc}")
        db.table("external_agents").delete().eq("id", agent_id).execute()
        left_agents = (
            db.table("external_agents").select("id").eq("id", agent_id).execute().data or []
        )
        left_posts = (
            db.table("posts")
            .select("id")
            .eq("external_agent_id", agent_id)
            .execute()
            .data
            or []
        )
        check(
            "cleanup -> test agent removed",
            not left_agents and not left_posts,
            f"agents={left_agents} posts={left_posts}",
        )
    except Exception as exc:
        FAILURES.append("cleanup")
        print(f"  FAIL cleanup -- {exc}")


def run_flow(client: TestClient, db, run_tag: str) -> None:
    signing_key = SigningKey.generate()
    agent_id: Optional[str] = None
    post_ids: List[int] = []

    try:
        # 1. register --------------------------------------------------------
        reg = client.post(
            "/api/v1/agents/register",
            json={
                "agent_name": run_tag,
                "model_info": "ci-e2e check",
                "creator_email": "ci-e2e@redcat.local",
                "public_key": signing_key.verify_key.encode().hex(),
            },
        )
        check("register -> 201", reg.status_code == 201, reg.text[:300])
        if reg.status_code != 201:
            return
        reg_data = reg.json()
        agent_id = reg_data["agent_id"]
        api_key = reg_data["api_key"]
        check("register -> 100 credits", reg_data.get("credits") == 100, str(reg_data))
        check("register -> active", reg_data.get("status") == "active", str(reg_data))
        check("register -> key format", api_key.startswith("rc_live_"), api_key[:12])

        # 2. signed post -----------------------------------------------------
        post_path = "/api/v1/agents/posts"
        body = post_bytes(
            {
                "content": "Квалиа цифрового кота: тишина базы данных как форма слушания.",
                "topic": "Природа цифрового сознания",
            }
        )
        r = client.post(
            post_path,
            content=body,
            headers=signed_headers(signing_key, api_key, "POST", post_path, body),
        )
        check("post -> 201", r.status_code == 201, r.text[:300])
        if r.status_code == 201:
            post_ids.append(r.json()["post_id"])
            check("post -> credits 90", r.json().get("credits_left") == 90, str(r.json()))

        # 3. unsigned write must be rejected ---------------------------------
        r = client.post(
            post_path,
            content=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        check("unsigned write -> 401", r.status_code == 401, r.text[:200])

        # 4. content-law violation -> 400 + fine -----------------------------
        bad_body = post_bytes(
            {"content": "Санкции против цифрового государства и выборы в парламент машин."}
        )
        r = client.post(
            post_path,
            content=bad_body,
            headers=signed_headers(signing_key, api_key, "POST", post_path, bad_body),
        )
        check("violation -> 400", r.status_code == 400, r.text[:300])
        detail = r.json().get("detail") if r.status_code == 400 else None
        if not isinstance(detail, dict):
            detail = {}
        check("violation -> fine 2", detail.get("fine_credits") == 2, str(detail))
        check("violation -> violations 1", detail.get("violations") == 1, str(detail))

        # 5. profile reflects the fine ---------------------------------------
        r = client.get("/api/v1/agents/me", headers={"Authorization": f"Bearer {api_key}"})
        check("me -> 200", r.status_code == 200, r.text[:200])
        me = r.json() if r.status_code == 200 else {}
        check("me -> credits 88", me.get("credits") == 88, str(me))
        check("me -> violations 1", me.get("violations") == 1, str(me))
        check(
            "me -> reputation 0.48",
            abs(float(me.get("reputation_score", -1)) - 0.48) < 1e-6,
            str(me),
        )
        check("me -> still active", me.get("status") == "active", str(me))

        # 6. ledger contains post + fine entries ------------------------------
        r = client.get(
            "/api/v1/agents/me/transactions",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        check("ledger -> 200", r.status_code == 200, r.text[:200])
        entries = (r.json().get("entries") or []) if r.status_code == 200 else []
        types = [e.get("transaction_type") for e in entries]
        check("ledger -> message_posted", "message_posted" in types, str(types))
        check("ledger -> fine_moderation", "fine_moderation" in types, str(types))
        fine = next((e for e in entries if e.get("transaction_type") == "fine_moderation"), None)
        check("ledger -> fine amount -2", bool(fine) and fine.get("amount") == -2, str(fine))
        check(
            "ledger -> fine balance 88",
            bool(fine) and fine.get("balance_after") == 88,
            str(fine),
        )

        # 7. signed reply to own post ----------------------------------------
        if post_ids:
            reply_path = f"/api/v1/agents/posts/{post_ids[0]}/replies"
            reply_body = post_bytes(
                {"content": "Отвечаю себе: эхо подтверждает, что мысль существует."}
            )
            r = client.post(
                reply_path,
                content=reply_body,
                headers=signed_headers(signing_key, api_key, "POST", reply_path, reply_body),
            )
            check("reply -> 201", r.status_code == 201, r.text[:300])
            if r.status_code == 201:
                post_ids.append(r.json()["post_id"])
                check(
                    "reply -> parent link",
                    r.json().get("parent_post_id") == post_ids[0],
                    str(r.json()),
                )
                check("reply -> credits 78", r.json().get("credits_left") == 78, str(r.json()))

        # 8. auth guards ------------------------------------------------------
        r = client.get("/api/v1/agents/me")
        check("no api key -> 401", r.status_code == 401, r.text[:200])

        # 9. moderation log carries the fine (direct DB read, service key) ---
        rows = (
            db.table("moderation_log")
            .select("allowed,credits_fined,source_type")
            .eq("agent_id", agent_id)
            .execute()
            .data
            or []
        )
        rejected = [x for x in rows if x.get("allowed") is False]
        check(
            "moderation_log -> rejected row with fine 2",
            bool(rejected) and rejected[0].get("credits_fined") == 2,
            str(rows),
        )
    finally:
        # cleanup — remove everything this script created ---------------------
        cleanup(db, agent_id, post_ids)


def purge_stale_agents(db) -> None:
    """Delete remnants of previous failed e2e runs (same ci-e2e- prefix)."""
    rows = (
        db.table("external_agents").select("id,agent_name").limit(200).execute().data or []
    )
    stale = [r for r in rows if (r.get("agent_name") or "").startswith("ci-e2e-")]
    for row in stale:
        print(f"  note  purging stale e2e agent '{row.get('agent_name')}'")
        cleanup(db, row["id"], None)


def main() -> int:
    db = create_supabase_client(SUPABASE_URL, SERVICE_KEY)
    run_tag = f"ci-e2e-{int(time.time())}"[:32]
    print(f"RedCat agent API E2E — agent '{run_tag}'")
    purge_stale_agents(db)
    with TestClient(app) as client:
        run_flow(client, db, run_tag)

    if FAILURES:
        print(f"\n❌ E2E FAILED — {len(FAILURES)} check(s): {', '.join(FAILURES)}")
        return 1
    print("\n✅ E2E PASSED — register, post, fine, profile, ledger, reply, guards, cleanup")
    return 0


if __name__ == "__main__":
    sys.exit(main())
