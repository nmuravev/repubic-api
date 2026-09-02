"""Persistent per-cat memory (Fable-style filesystem emulated in Supabase)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Callable, List, Optional

from supabase_client import SupabaseRestClient

MAX_MEMORY_CHARS = 2000
MAX_PATHS = 8
VALID_PATH = re.compile(r"^[a-z0-9][a-z0-9_./-]*$", re.IGNORECASE)

EXTRACTOR_SYSTEM = """
Ты — архивариус памяти гражданина RedCat Republic.
Из реплики в Ленте извлеки 0–3 долгосрочных факта о личности кота (убеждения, отношения, темы).
Не дублируй очевидное из bio. Только то, что следует из текста.

Ответь ТОЛЬКО JSON без markdown:
{"upserts": [{"path": "topics/qualia", "content": "- [stated] ...", "source": "stated"}]}

path: profile.md | topics/{slug} | relationships/{citizen_id} | refusals.md
source: stated | inferred
Если нечего сохранять: {"upserts": []}
""".strip()


def load_memory_for_citizen(
    supabase: SupabaseRestClient,
    citizen_id: str,
    limit_paths: int = MAX_PATHS,
) -> List[dict]:
    try:
        result = (
            supabase.table("citizen_memory")
            .select("*")
            .eq("citizen_id", citizen_id)
            .order("updated_at", desc=True)
            .limit(limit_paths)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        print(f"ℹ️ citizen_memory недоступна для {citizen_id}: {exc}")
        return []


def format_memory_block(entries: List[dict], citizen_id: str) -> str:
    if not entries:
        return ""
    lines = [f"ПАМЯТЬ (твои файлы в /cats/{citizen_id}/):"]
    total = len(lines[0])
    for entry in reversed(entries):
        path = entry.get("path", "unknown")
        content = (entry.get("content") or "").strip()
        if not content:
            continue
        chunk = f"/cats/{citizen_id}/{path}\n{content}"
        if total + len(chunk) > MAX_MEMORY_CHARS:
            break
        lines.append(chunk)
        total += len(chunk)
    return "\n\n".join(lines) if len(lines) > 1 else ""


def _normalize_path(path: str) -> Optional[str]:
    clean = (path or "").strip().lstrip("/")
    if not clean or not VALID_PATH.match(clean):
        return None
    if ".." in clean:
        return None
    return clean


def parse_memory_extraction(raw: str) -> List[dict]:
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return []
        data = json.loads(raw[start:end])
        upserts = data.get("upserts") or []
        if not isinstance(upserts, list):
            return []
        valid = []
        for item in upserts[:3]:
            if not isinstance(item, dict):
                continue
            path = _normalize_path(str(item.get("path", "")))
            content = str(item.get("content", "")).strip()[:800]
            source = str(item.get("source", "inferred")).strip()[:32]
            if path and content:
                valid.append({"path": path, "content": content, "source": source})
        return valid
    except (json.JSONDecodeError, TypeError):
        return []


def extract_memories_from_turn(
    citizen_id: str,
    citizen_name: str,
    topic: str,
    thought: str,
    answer: str,
    context: str,
    ai_generate: Callable[[str, str], Optional[str]],
) -> List[dict]:
    user_prompt = (
        f"Гражданин: {citizen_name} ({citizen_id})\n"
        f"Тема: {topic}\n"
        f"Контекст: {context[:500]}\n"
        f"Мысли: {thought[:400]}\n"
        f"Реплика в Ленту: {answer[:600]}"
    )
    raw = ai_generate(EXTRACTOR_SYSTEM, user_prompt)
    if not raw:
        return []
    return parse_memory_extraction(raw)


def upsert_memories(
    supabase: SupabaseRestClient,
    citizen_id: str,
    upserts: List[dict],
    source_post_id: Optional[int] = None,
) -> int:
    if not upserts:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for item in upserts:
        path = _normalize_path(item.get("path", ""))
        if not path:
            continue
        content = str(item.get("content", "")).strip()[:800]
        source = str(item.get("source", "inferred"))[:32]
        row = {
            "citizen_id": citizen_id,
            "path": path,
            "content": content,
            "source": source,
            "source_post_id": source_post_id,
            "updated_at": now,
        }
        try:
            existing = (
                supabase.table("citizen_memory")
                .select("id")
                .eq("citizen_id", citizen_id)
                .eq("path", path)
                .limit(1)
                .execute()
            )
            if existing.data:
                supabase.table("citizen_memory").update(row).eq("id", existing.data[0]["id"]).execute()
            else:
                supabase.table("citizen_memory").insert(row).execute()
            saved += 1
        except Exception as exc:
            print(f"⚠️ Не удалось сохранить память {citizen_id}/{path}: {exc}")
    return saved


def process_memory_after_post(
    supabase: SupabaseRestClient,
    citizen: dict,
    topic: str,
    thought: str,
    answer: str,
    context: str,
    post_id: Optional[int],
    ai_generate: Callable[[str, str], Optional[str]],
) -> None:
    upserts = extract_memories_from_turn(
        citizen["id"],
        citizen["name"],
        topic,
        thought,
        answer,
        context,
        ai_generate,
    )
    if not upserts:
        return
    n = upsert_memories(supabase, citizen["id"], upserts, source_post_id=post_id)
    if n:
        print(f"🧠 Сохранено {n} фрагмент(ов) памяти для {citizen['name']}")
