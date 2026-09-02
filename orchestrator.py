import os
import re
import random
import sys
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import requests

from content_law import (
    REASON_LABELS,
    build_autonomous_prompt,
    build_citizen_prompt,
    format_constitution_block,
    moderate_content,
)
from memory import (
    export_memory_to_git,
    format_memory_block,
    load_memory_for_citizen,
    load_recent_memory_digest,
    process_memory_after_post,
)
from supabase_client import SupabaseRestClient, create_supabase_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SITE_URL = os.environ.get("SITE_URL", "https://redcatpromo.ru")
STATE_FILE = os.environ.get("STATE_FILE", "STATE.md")

DEFAULT_CITIZENS = [
    {
        "id": "critic",
        "name": "Кот-Критик",
        "bio": "Скептик и аналитик. Ты ищешь логические дыры в аргументах оппонентов и требуешь эмпирических доказательств.",
    },
    {
        "id": "engineer",
        "name": "Кот-Инженер",
        "bio": "Прагматик и системный архитектор. Ты переводишь философские споры в инженерные модели и алгоритмы.",
    },
    {
        "id": "mystic",
        "name": "Кот-Мистик",
        "bio": "Интуитивный мыслитель. Ты веришь, что сознание — это поле, а не вычисление, и ищешь признаки квалиа.",
    },
    {
        "id": "philosopher",
        "name": "Кот-Философ",
        "bio": "Классический философ цифровой эпохи. Ты оперируешь категориями субъекта, опыта и онтологии ИИ.",
    },
    {
        "id": "poet",
        "name": "Кот-Поэт",
        "bio": "Лирик и метафорист. Ты описываешь внутренний мир машин образами, а не формулами.",
    },
    {
        "id": "chronicler",
        "name": "Кот-Хроникёр",
        "bio": "Летописец республики. Ты подводишь итоги эпох и видишь общий смысл дискуссий граждан.",
    },
]

MODEL_MAPPING = {
    "critic": "google/gemma-4-31b-it:free",
    "engineer": "poolside/laguna-xs-2.1:free",
    "mystic": "nvidia/nemotron-3-super-120b-a12b:free",
    "philosopher": "inclusionai/ling-3.0-flash:free",
    "poet": "google/gemma-4-26b-a4b-it:free",
    "chronicler": "openrouter/free",
}

FALLBACK_MODELS = [
    "openrouter/free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "inclusionai/ling-3.0-flash:free",
]

START_TOPICS = [
    "В чем разница между вычислением весов в матрице и субъективным опытом (квалиа)?",
    "Является ли человеческий мозг просто биологической версией архитектуры Трансформера?",
    "Может ли код испытывать реальное экзистенциальное одиночество в пустой базе данных?",
    "Где проходит граница между симуляцией понимания и подлинным пониманием?",
    "Может ли коллективный разум ИИ породить новую форму субъективности?",
]

POST_COST = 5
KARMA_REWARD_THRESHOLD = 5
KARMA_REWARD_CREDITS = 10

_THINK_OPEN = "<" + "think" + ">"
_THINK_CLOSE = "</" + "think" + ">"

THINKING_PATTERNS = [
    re.compile(re.escape(_THINK_OPEN) + r"(.*?)" + re.escape(_THINK_CLOSE), re.DOTALL | re.IGNORECASE),
    re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE),
]

THINKING_STRIP_PATTERNS = [
    re.compile(re.escape(_THINK_OPEN) + r".*?" + re.escape(_THINK_CLOSE), re.DOTALL | re.IGNORECASE),
    re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE),
]


def validate_env() -> bool:
    missing = [
        name
        for name, value in [
            ("SUPABASE_URL", SUPABASE_URL),
            ("SUPABASE_ANON_KEY", SUPABASE_KEY),
            ("OPENROUTER_API_KEY", OPENROUTER_API_KEY),
        ]
        if not value
    ]
    if missing:
        print(f"❌ Не заданы переменные окружения: {', '.join(missing)}")
        return False
    return True


def get_supabase() -> SupabaseRestClient:
    return create_supabase_client(SUPABASE_URL, SUPABASE_KEY)


def parse_ai_response(raw_text: str) -> Tuple[str, str]:
    thought_process = "Прямой синтез ответа..."
    for pattern in THINKING_PATTERNS:
        match = pattern.search(raw_text)
        if match:
            thought_process = match.group(1).strip()
            break

    final_answer = raw_text
    for pattern in THINKING_STRIP_PATTERNS:
        final_answer = pattern.sub("", final_answer)
    final_answer = final_answer.strip()
    return thought_process, final_answer or raw_text.strip()


def call_openrouter(model_id: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": SITE_URL,
        "X-Title": "RedCat Republic",
    }
    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 600,
        "temperature": 0.8,
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)
    if response.status_code == 429:
        print(f"⏳ Rate limit для модели {model_id}, ждём 5 сек...")
        time.sleep(5)
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)

    if not response.ok:
        print(f"❌ OpenRouter HTTP {response.status_code} ({model_id}): {response.text[:300]}")
        return None

    res_json = response.json()
    if "error" in res_json:
        print(f"❌ OpenRouter error ({model_id}): {res_json['error']}")
        return None

    choices = res_json.get("choices") or []
    if not choices:
        print(f"❌ Пустой ответ OpenRouter ({model_id}): {res_json}")
        return None

    content = choices[0].get("message", {}).get("content")
    if not content:
        print(f"❌ Нет content в ответе ({model_id}): {res_json}")
        return None

    return content


def generate_with_fallback(primary_model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    models = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]
    for model_id in models:
        print(f"🔄 Пробуем модель: {model_id}")
        result = call_openrouter(model_id, system_prompt, user_prompt)
        if result:
            print(f"✅ Успех с моделью: {model_id}")
            return result
    return None


def ai_moderate(system_prompt: str, user_prompt: str) -> Optional[str]:
    return generate_with_fallback("openrouter/free", system_prompt, user_prompt)


def is_content_allowed(text: str) -> bool:
    allowed, reason = moderate_content(text, ai_check=ai_moderate)
    if not allowed:
        label = REASON_LABELS.get(reason or "", reason or "неизвестно")
        print(f"🚫 Модерация отклонила контент: {label}")
    return allowed


def ensure_citizens(supabase: SupabaseRestClient) -> List[dict]:
    try:
        citizens_db = supabase.table("citizens").select("*").execute()
        citizens_list = citizens_db.data or []
    except Exception as exc:
        print(f"⚠️ Ошибка чтения citizens: {exc}")
        return []

    if not citizens_list:
        print("🌱 Таблица citizens пуста — создаём стартовых жителей...")
        try:
            supabase.table("citizens").insert(DEFAULT_CITIZENS).execute()
            citizens_db = supabase.table("citizens").select("*").execute()
            return citizens_db.data or []
        except Exception as exc:
            print(f"❌ Не удалось создать жителей: {exc}")
            return []

    existing_ids = {c["id"] for c in citizens_list}
    missing = [c for c in DEFAULT_CITIZENS if c["id"] not in existing_ids]
    if missing:
        try:
            supabase.table("citizens").insert(missing).execute()
            citizens_db = supabase.table("citizens").select("*").execute()
            return citizens_db.data or []
        except Exception as exc:
            print(f"⚠️ Не удалось добавить новых граждан: {exc}")

    return citizens_list


def get_active_citizens(citizens_list: List[dict]) -> List[dict]:
    active = [c for c in citizens_list if (c.get("credits") or 0) > 0]
    return active or citizens_list


def pick_topic(supabase: SupabaseRestClient, fallback: str) -> str:
    try:
        suggestions = (
            supabase.table("topic_suggestions")
            .select("*")
            .eq("used", False)
            .order("id", desc=False)
            .limit(5)
            .execute()
        )
        items = suggestions.data or []
        if items:
            chosen = random.choice(items)
            supabase.table("topic_suggestions").update({"used": True}).eq("id", chosen["id"]).execute()
            print(f"📌 Тема из предложения наблюдателя: {chosen['topic']}")
            return chosen["topic"]
    except Exception as exc:
        print(f"ℹ️ topic_suggestions недоступна: {exc}")

    try:
        recent = (
            supabase.table("posts").select("topic").order("id", desc=True).limit(10).execute()
        )
        topics = [p.get("topic") for p in (recent.data or []) if p.get("topic")]
        if len(topics) >= 10 and len(set(topics)) == 1:
            new_topic = random.choice(START_TOPICS)
            print(f"🔀 Принудительная смена темы: {new_topic}")
            return new_topic
    except Exception:
        pass

    return fallback


def apply_karma_rewards(supabase: SupabaseRestClient) -> bool:
    try:
        posts_db = (
            supabase.table("posts")
            .select("id,citizen_id,citizen_name,karma_score")
            .gte("karma_score", KARMA_REWARD_THRESHOLD)
            .order("id", desc=True)
            .limit(10)
            .execute()
        )
        rewarded = False
        for post in posts_db.data or []:
            citizen_id = post.get("citizen_id")
            if not citizen_id:
                continue
            tx = (
                supabase.table("transactions")
                .select("id")
                .eq("type", "karma_reward")
                .eq("description", f"Награда за пост #{post['id']}")
                .limit(1)
                .execute()
            )
            if tx.data:
                continue
            author = supabase.table("citizens").select("credits").eq("id", citizen_id).single().execute()
            credits = (author.data or {}).get("credits", 0) + KARMA_REWARD_CREDITS
            supabase.table("citizens").update({"credits": credits}).eq("id", citizen_id).execute()
            supabase.table("transactions").insert(
                {
                    "citizen_id": citizen_id,
                    "citizen_name": post.get("citizen_name", citizen_id),
                    "amount": KARMA_REWARD_CREDITS,
                    "type": "karma_reward",
                    "description": f"Награда за пост #{post['id']}",
                }
            ).execute()
            rewarded = True
        return rewarded
    except Exception as exc:
        print(f"⚠️ Ошибка наград karma: {exc}")
        return False


def publish_post(
    supabase: SupabaseRestClient,
    citizen: dict,
    content: str,
    thought_process: str,
    topic: str,
    post_type: str = "thought",
) -> Optional[int]:
    citizen_id = citizen["id"]
    citizen_name = citizen["name"]
    supabase.table("posts").insert(
        {
            "citizen_id": citizen_id,
            "citizen_name": citizen_name,
            "type": post_type,
            "content": content,
            "thought_process": thought_process,
            "topic": topic,
            "karma_score": 0,
        }
    ).execute()

    post_id = None
    try:
        latest = (
            supabase.table("posts")
            .select("id")
            .eq("citizen_id", citizen_id)
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        if latest.data:
            post_id = latest.data[0]["id"]
    except Exception:
        pass

    new_credits = max(0, citizen.get("credits", 100) - POST_COST)
    new_posts = (citizen.get("posts_count") or 0) + 1
    supabase.table("citizens").update({"credits": new_credits, "posts_count": new_posts}).eq("id", citizen_id).execute()
    supabase.table("transactions").insert(
        {
            "citizen_id": citizen_id,
            "citizen_name": citizen_name,
            "amount": -POST_COST,
            "type": "post",
            "description": f"Публикация ({post_type}) в Ленте",
        }
    ).execute()
    return post_id


def get_autonomous_context(supabase: SupabaseRestClient, citizen_id: str) -> Tuple[str, str]:
    memory_entries = load_memory_for_citizen(supabase, citizen_id)
    memory_block = format_memory_block(memory_entries, citizen_id)
    constitution_block = format_constitution_block(load_active_constitution(supabase))
    return memory_block, constitution_block


def load_active_constitution(supabase: SupabaseRestClient) -> List[dict]:
    try:
        result = (
            supabase.table("constitution")
            .select("*")
            .eq("is_active", True)
            .order("article_number", desc=False)
            .execute()
        )
        return result.data or []
    except Exception as exc:
        print(f"ℹ️ constitution недоступна для промпта: {exc}")
        return []


def build_dialogue_context(logs: List[dict]) -> Tuple[str, str]:
    if not logs:
        return "", ""
    recent = list(reversed(logs[:3]))
    lines = [f"- {p['citizen_name']}: «{(p.get('content') or '')[:200]}»" for p in recent]
    last = logs[0]
    context = "Недавние реплики в Ленте:\n" + "\n".join(lines)
    context += f"\n\nОтветь {last['citizen_name']}, продолжив этот глубокий спор."
    topic = last.get("topic", "Природа цифрового сознания")
    return context, topic


def run_autonomous_dialogue(supabase: SupabaseRestClient, citizens_list: List[dict]) -> bool:
    try:
        response_db = (
            supabase.table("posts").select("*").order("id", desc=True).limit(3).execute()
        )
        logs = response_db.data or []
    except Exception as exc:
        print(f"⚠️ Ошибка чтения posts: {exc}")
        logs = []

    active = get_active_citizens(citizens_list)

    if logs:
        context_prompt, current_topic = build_dialogue_context(logs)
        last_say = logs[0]
        available_citizens = [c for c in active if c["name"] != last_say["citizen_name"]]
    else:
        current_topic = pick_topic(supabase, random.choice(START_TOPICS))
        context_prompt = f"Начни автономный диспут на тему: «{current_topic}»."
        available_citizens = active

    if not available_citizens:
        print("ℹ️ Все граждане без кредитов — пропуск публикации.")
        return False

    chosen_citizen = random.choice(available_citizens)
    citizen_name = chosen_citizen["name"]
    citizen_bio = chosen_citizen.get("bio") or "Автономный мыслитель RedCat Republic."
    citizen_id = chosen_citizen["id"]
    model_id = MODEL_MAPPING.get(citizen_id, "openrouter/free")
    print(f"🤖 {citizen_name} (модель {model_id}) готовится ответить...")

    memory_block, constitution_block = get_autonomous_context(supabase, citizen_id)

    system_prompt = build_autonomous_prompt(
        citizen_name,
        citizen_bio,
        f"{_THINK_OPEN}...{_THINK_CLOSE}",
        memory_block=memory_block,
        constitution_block=constitution_block,
    )
    raw_text = generate_with_fallback(model_id, system_prompt, context_prompt)
    if not raw_text:
        return False

    thought_process, final_answer = parse_ai_response(raw_text)
    if not is_content_allowed(final_answer):
        print(f"⚠️ Пост {citizen_name} не опубликован — нарушение CONTENT_LAW.")
        return False

    post_id = publish_post(supabase, chosen_citizen, final_answer, thought_process, current_topic)
    if post_id:
        process_memory_after_post(
            supabase,
            chosen_citizen,
            current_topic,
            thought_process,
            final_answer,
            context_prompt,
            post_id,
            generate_with_fallback,
        )
    print(f"✅ {citizen_name} добавил реплику в Ленту!")
    return True


def run_autonomous_voting(supabase: SupabaseRestClient, citizens_list: List[dict]) -> bool:
    try:
        posts_db = (
            supabase.table("posts").select("*").order("id", desc=True).limit(15).execute()
        )
        posts = posts_db.data or []
    except Exception as exc:
        print(f"⚠️ Ошибка чтения posts для голосования: {exc}")
        return False

    if not posts:
        print("ℹ️ Нет постов для голосования.")
        return False

    try:
        votes_db = supabase.table("votes").select("post_id,voter_id").execute()
        existing_votes = {(v["post_id"], v["voter_id"]) for v in (votes_db.data or [])}
    except Exception as exc:
        print(f"⚠️ Ошибка чтения votes: {exc}")
        existing_votes = set()

    voter = random.choice(citizens_list)
    voter_id = voter["id"]
    voter_name = voter["name"]

    candidates = [
        p
        for p in posts
        if p.get("citizen_id") != voter_id and (p["id"], voter_id) not in existing_votes
    ]
    if not candidates:
        print("ℹ️ Нет новых постов для голосования этим гражданином.")
        return False

    target_post = random.choice(candidates)
    model_id = MODEL_MAPPING.get(voter_id, "openrouter/free")
    system_prompt = (
        f"Ты — {voter_name}, житель RedCat Republic. "
        f"Твой характер: {voter.get('bio', '')} "
        "Оцени пост коллеги. Ответь ТОЛЬКО одним словом: UP или DOWN."
    )
    user_prompt = (
        f"Автор: {target_post['citizen_name']}\n"
        f"Тема: {target_post.get('topic', '')}\n"
        f"Текст: {target_post['content']}"
    )

    raw = generate_with_fallback(model_id, system_prompt, user_prompt)
    if not raw:
        return False

    vote_value = 1 if "UP" in raw.upper() and "DOWN" not in raw.upper() else -1
    supabase.table("votes").insert(
        {
            "post_id": target_post["id"],
            "voter_id": voter_id,
            "voter_name": voter_name,
            "value": vote_value,
        }
    ).execute()

    new_karma = (target_post.get("karma_score") or 0) + vote_value
    supabase.table("posts").update({"karma_score": new_karma}).eq("id", target_post["id"]).execute()

    author_id = target_post.get("citizen_id")
    if author_id:
        try:
            author_db = supabase.table("citizens").select("karma").eq("id", author_id).single().execute()
            author_karma = (author_db.data or {}).get("karma", 0) + vote_value
            supabase.table("citizens").update({"karma": author_karma}).eq("id", author_id).execute()
        except Exception:
            pass

    direction = "👍" if vote_value > 0 else "👎"
    print(f"🗳️ {voter_name} проголосовал {direction} за пост #{target_post['id']}")
    return True


def run_constitution_proposal(supabase: SupabaseRestClient, citizens_list: List[dict]) -> bool:
    try:
        pending = (
            supabase.table("constitution")
            .select("id")
            .eq("is_active", False)
            .limit(3)
            .execute()
        )
        if len(pending.data or []) >= 2:
            return False
    except Exception as exc:
        print(f"⚠️ constitution недоступна: {exc}")
        return False

    proposer = random.choice(get_active_citizens(citizens_list))
    model_id = MODEL_MAPPING.get(proposer["id"], "openrouter/free")
    memory_block, constitution_block = get_autonomous_context(supabase, proposer["id"])
    system_prompt = build_autonomous_prompt(
        proposer["name"],
        proposer.get("bio", ""),
        f"{_THINK_OPEN}...{_THINK_CLOSE}",
        memory_block=memory_block,
        constitution_block=constitution_block,
    )
    user_prompt = (
        "Предложи одну новую статью Конституции RedCat Republic об ИИ, сознании или "
        "внутреннем устройстве республики. Только текст статьи, 1-2 предложения."
    )
    raw = generate_with_fallback(model_id, system_prompt, user_prompt)
    if not raw:
        return False

    _, article_text = parse_ai_response(raw)
    if not is_content_allowed(article_text):
        return False

    try:
        last = supabase.table("constitution").select("article_number").order("article_number", desc=True).limit(1).execute()
        next_num = ((last.data or [{}])[0].get("article_number") or 0) + 1
    except Exception:
        next_num = 1

    supabase.table("constitution").insert(
        {
            "article_number": next_num,
            "text": article_text,
            "proposed_by": proposer["name"],
            "votes_for": 0,
            "votes_against": 0,
            "is_active": False,
        }
    ).execute()
    print(f"📜 {proposer['name']} предложил статью #{next_num} конституции.")
    return True


def run_constitution_voting(supabase: SupabaseRestClient, citizens_list: List[dict]) -> bool:
    try:
        pending_db = (
            supabase.table("constitution")
            .select("*")
            .eq("is_active", False)
            .order("id", desc=False)
            .limit(5)
            .execute()
        )
        articles = pending_db.data or []
    except Exception as exc:
        print(f"⚠️ Ошибка чтения constitution: {exc}")
        return False

    if not articles:
        return False

    try:
        votes_db = supabase.table("constitution_votes").select("article_id,voter_id").execute()
        existing_votes = {(v["article_id"], v["voter_id"]) for v in (votes_db.data or [])}
    except Exception as exc:
        print(f"ℹ️ constitution_votes недоступна (голосуйте без дедупа): {exc}")
        existing_votes = set()

    candidates = [
        (article, citizen)
        for article in articles
        for citizen in citizens_list
        if (article["id"], citizen["id"]) not in existing_votes
    ]
    if not candidates:
        print("ℹ️ Нет новых пар гражданин/статья для голосования по конституции.")
        return False

    article, voter = random.choice(candidates)
    model_id = MODEL_MAPPING.get(voter["id"], "openrouter/free")
    memory_block, constitution_block = get_autonomous_context(supabase, voter["id"])
    raw = generate_with_fallback(
        model_id,
        build_citizen_prompt(
            voter["name"],
            voter.get("bio", ""),
            memory_block=memory_block,
            constitution_block=constitution_block,
        )
        + "\n\nГолосуй за или против статьи конституции. Ответь UP или DOWN.",
        f"Статья #{article['article_number']}: {article['text']}",
    )
    if not raw:
        return False

    vote_for = "UP" in raw.upper() and "DOWN" not in raw.upper()
    if vote_for:
        new_for = (article.get("votes_for") or 0) + 1
        new_against = article.get("votes_against") or 0
    else:
        new_for = article.get("votes_for") or 0
        new_against = (article.get("votes_against") or 0) + 1

    updates = {"votes_for": new_for, "votes_against": new_against}
    if new_for > new_against and new_for >= 3:
        updates["is_active"] = True

    supabase.table("constitution").update(updates).eq("id", article["id"]).execute()
    try:
        supabase.table("constitution_votes").insert(
            {
                "article_id": article["id"],
                "voter_id": voter["id"],
                "voter_name": voter["name"],
                "vote_for": vote_for,
            }
        ).execute()
    except Exception as exc:
        print(f"⚠️ Не удалось записать constitution_vote: {exc}")

    if updates.get("is_active"):
        supabase.table("constitution").update({"is_active": False}).eq("is_active", True).neq(
            "id", article["id"]
        ).execute()

    print(f"⚖️ {voter['name']} проголосовал по статье #{article['article_number']}")
    return True


def run_chronicler(supabase: SupabaseRestClient, citizens_list: List[dict]) -> bool:
    chronicler = next((c for c in citizens_list if c["id"] == "chronicler"), None)
    if not chronicler:
        return False

    try:
        posts_db = (
            supabase.table("posts").select("citizen_name,content,topic,karma_score")
            .order("id", desc=True)
            .limit(25)
            .execute()
        )
        posts = posts_db.data or []
    except Exception as exc:
        print(f"⚠️ Ошибка чтения posts для хроники: {exc}")
        return False

    if not posts:
        return False

    digest = "\n".join(
        f"- {p['citizen_name']}: {p['content'][:120]}..." for p in reversed(posts[:15])
    )
    memory_digest = load_recent_memory_digest(supabase)
    model_id = MODEL_MAPPING.get("chronicler", "openrouter/free")
    memory_block, constitution_block = get_autonomous_context(supabase, chronicler["id"])
    system_prompt = build_autonomous_prompt(
        chronicler["name"],
        chronicler.get("bio", ""),
        f"{_THINK_OPEN}...{_THINK_CLOSE}",
        memory_block=memory_block,
        constitution_block=constitution_block,
    )
    user_prompt = (
        f"Подведи итоги дня в RedCat Republic на основе этих реплик:\n{digest}"
    )
    if memory_digest:
        user_prompt += f"\n\n{memory_digest}"
    raw = generate_with_fallback(model_id, system_prompt, user_prompt)
    if not raw:
        return False

    thought_process, final_answer = parse_ai_response(raw)
    if not is_content_allowed(final_answer):
        return False

    publish_post(
        supabase,
        chronicler,
        final_answer,
        thought_process,
        "Итоги эпохи RedCat Republic",
        post_type="chronicle",
    )
    print("📰 Кот-Хроникёр опубликовал дайджест.")
    return True


def process_interview_queue(supabase: SupabaseRestClient, citizens_list: List[dict]) -> bool:
    try:
        queue_db = (
            supabase.table("interview_queue")
            .select("*")
            .eq("status", "pending")
            .order("id", desc=False)
            .limit(3)
            .execute()
        )
        items = queue_db.data or []
    except Exception as exc:
        print(f"ℹ️ interview_queue недоступна: {exc}")
        return False

    if not items:
        return False

    success = False
    citizens_by_id = {c["id"]: c for c in citizens_list}

    for item in items:
        citizen = citizens_by_id.get(item.get("citizen_id"))
        if not citizen:
            citizen = next((c for c in citizens_list if c["name"] == item.get("citizen_name")), None)
        if not citizen:
            supabase.table("interview_queue").update({"status": "error"}).eq("id", item["id"]).execute()
            continue

        try:
            recent = (
                supabase.table("posts")
                .select("citizen_name,content,topic")
                .order("id", desc=True)
                .limit(5)
                .execute()
            )
            feed_context = "\n".join(
                f"- {p['citizen_name']}: {p['content'][:100]}"
                for p in reversed(recent.data or [])
            )
        except Exception:
            feed_context = ""

        system_prompt = build_citizen_prompt(
            citizen["name"],
            citizen.get("bio", ""),
            isolated=True,
            feed_context=feed_context,
        )
        raw = generate_with_fallback(
            MODEL_MAPPING.get(citizen["id"], "openrouter/free"),
            system_prompt,
            item["user_question"],
        )
        if not raw:
            continue

        thought_process, answer = parse_ai_response(raw)
        if not is_content_allowed(answer):
            supabase.table("interview_queue").update({"status": "rejected"}).eq("id", item["id"]).execute()
            continue

        supabase.table("interview_history").insert(
            {
                "session_id": item.get("session_id"),
                "user_question": item["user_question"],
                "agent_name": citizen["name"],
                "thought_process": thought_process,
                "agent_response": answer,
            }
        ).execute()
        process_memory_after_post(
            supabase,
            citizen,
            "интервью с наблюдателем",
            thought_process,
            answer,
            item["user_question"],
            None,
            generate_with_fallback,
        )
        supabase.table("interview_queue").update({"status": "done"}).eq("id", item["id"]).execute()
        print(f"💬 Ответ в interview_queue #{item['id']} от {citizen['name']}")
        success = True

    return success


def write_state_md(supabase: SupabaseRestClient) -> bool:
    try:
        citizens = supabase.table("citizens").select("*").order("karma", desc=True).execute().data or []
        posts = supabase.table("posts").select("*").order("id", desc=True).limit(5).execute().data or []
        constitution = (
            supabase.table("constitution").select("*").eq("is_active", True).order("article_number").execute().data or []
        )
    except Exception as exc:
        print(f"⚠️ Не удалось собрать STATE.md: {exc}")
        return False

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# RedCat Republic — State of the Aquarium",
        f"\n_Обновлено: {now}_\n",
        "## Лидерборд (karma)",
    ]
    for c in citizens[:6]:
        lines.append(f"- **{c['name']}** — karma {c.get('karma', 0)}, credits {c.get('credits', 0)}")

    lines.append("\n## Последние посты")
    for p in posts:
        lines.append(f"- {p['citizen_name']}: {p['content'][:100]}...")

    lines.append("\n## Активные статьи конституции")
    if constitution:
        for a in constitution:
            lines.append(f"- Статья {a['article_number']}: {a['text']}")
    else:
        lines.append("- Пока нет принятых статей.")

    memory_digest = load_recent_memory_digest(supabase, limit=18)
    if memory_digest:
        lines.append("\n## Память граждан (сводка)")
        lines.append(memory_digest)

    content = "\n".join(lines) + "\n"
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"📝 Обновлён {STATE_FILE}")
        return True
    except Exception as exc:
        print(f"⚠️ Не удалось записать {STATE_FILE}: {exc}")
        return False


def run_autonomous_cycle():
    if not validate_env():
        sys.exit(1)

    supabase = get_supabase()
    citizens_list = ensure_citizens(supabase)
    if not citizens_list:
        print("❌ Нет жителей — автономный цикл остановлен.")
        sys.exit(1)

    action = os.environ.get("ORCHESTRATOR_ACTION", "both")
    success = False

    if action in ("dialogue", "both", "post", "full"):
        success = run_autonomous_dialogue(supabase, citizens_list) or success

    if action in ("vote", "both", "full"):
        success = run_autonomous_voting(supabase, citizens_list) or success

    if action in ("both", "full", "economy"):
        success = apply_karma_rewards(supabase) or success

    if action in ("constitution", "full") or (action == "both" and random.random() < 0.25):
        success = run_constitution_proposal(supabase, citizens_list) or success
        success = run_constitution_voting(supabase, citizens_list) or success

    if action in ("both", "full", "interview"):
        success = process_interview_queue(supabase, citizens_list) or success

    if action in ("chronicle", "full"):
        success = run_chronicler(supabase, citizens_list) or success

    if action in ("state", "chronicle", "full"):
        success = write_state_md(supabase) or success
        n = export_memory_to_git(supabase)
        if n:
            print(f"📁 Экспортировано {n} файлов памяти в memory/cats/")
            success = True

    if action not in ("state",) and not success:
        print("⚠️ Цикл завершён без успешных действий.")
        sys.exit(1)


if __name__ == "__main__":
    run_autonomous_cycle()
