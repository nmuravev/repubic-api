"""Moderation audit log and citizen counters for RedCat Republic."""

from __future__ import annotations

from typing import Optional

from supabase_client import SupabaseRestClient

PREVIEW_LEN = 240


def log_moderation_decision(
    supabase: SupabaseRestClient,
    *,
    allowed: bool,
    content: str,
    source_type: str,
    reason: Optional[str] = None,
    judge_method: str = "regex",
    citizen_id: Optional[str] = None,
    citizen_name: Optional[str] = None,
    source_id: Optional[int] = None,
) -> None:
    preview = (content or "").strip()[:PREVIEW_LEN]
    if not preview:
        return
    row = {
        "source_type": source_type,
        "source_id": source_id,
        "citizen_id": citizen_id,
        "citizen_name": citizen_name,
        "content_preview": preview,
        "allowed": allowed,
        "reason": reason,
        "judge_method": judge_method,
        "judge_name": "Кот-Критик" if judge_method == "critic_ai" else "CONTENT_LAW",
    }
    try:
        supabase.table("moderation_log").insert(row).execute()
    except Exception as exc:
        print(f"ℹ️ moderation_log недоступен: {exc}")
        return

    if not citizen_id:
        return
    field = "moderation_passed" if allowed else "moderation_blocked"
    try:
        current = (
            supabase.table("citizens")
            .select(field)
            .eq("id", citizen_id)
            .limit(1)
            .execute()
        )
        value = ((current.data or [{}])[0].get(field) or 0) + 1
        supabase.table("citizens").update({field: value}).eq("id", citizen_id).execute()
    except Exception as exc:
        print(f"ℹ️ Не удалось обновить счётчик модерации для {citizen_id}: {exc}")
