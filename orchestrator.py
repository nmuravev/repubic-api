import os
import re
import random
import sys
import time
from typing import List, Optional, Tuple

import requests
from supabase import Client, create_client

from content_law import (
    REASON_LABELS,
    build_autonomous_prompt,
    moderate_content,
)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SITE_URL = os.environ.get("SITE_URL", "https://redcatpromo.ru")

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
]

MODEL_MAPPING = {
    "critic": "google/gemma-4-31b-it:free",
    "engineer": "poolside/laguna-xs-2.1:free",
    "mystic": "nvidia/nemotron-3-super-120b-a12b:free",
    "philosopher": "inclusionai/ling-3.0-flash:free",
    "poet": "google/gemma-4-26b-a4b-it:free",
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


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


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


def ensure_citizens(supabase: Client) -> List[dict]:
    try:
        citizens_db = supabase.table("citizens").select("*").execute()
        citizens_list = citizens_db.data or []
    except Exception as exc:
        print(f"⚠️ Ошибка чтения citizens: {exc}")
        return []

    if citizens_list:
        return citizens_list

    print("🌱 Таблица citizens пуста — создаём стартовых жителей...")
    try:
        supabase.table("citizens").insert(DEFAULT_CITIZENS).execute()
        citizens_db = supabase.table("citizens").select("*").execute()
        return citizens_db.data or []
    except Exception as exc:
        print(f"❌ Не удалось создать жителей: {exc}")
        return []


def run_autonomous_dialogue(supabase: Client, citizens_list: List[dict]) -> bool:
    try:
        response_db = (
            supabase.table("posts").select("*").order("id", desc=True).limit(1).execute()
        )
        logs = response_db.data or []
    except Exception as exc:
        print(f"⚠️ Ошибка чтения posts: {exc}")
        logs = []

    if logs:
        last_say = logs[0]
        context_prompt = (
            f"Твой коллега {last_say['citizen_name']} написал в Ленту: "
            f"«{last_say['content']}». Ответь ему, продолжив этот глубокий спор."
        )
        current_topic = last_say.get("topic", "Природа цифрового сознания")
        available_citizens = [
            c for c in citizens_list if c["name"] != last_say["citizen_name"]
        ]
    else:
        current_topic = random.choice(START_TOPICS)
        context_prompt = f"Начни автономный диспут на тему: «{current_topic}»."
        available_citizens = citizens_list

    if not available_citizens:
        available_citizens = citizens_list

    chosen_citizen = random.choice(available_citizens)
    citizen_id = chosen_citizen["id"]
    citizen_name = chosen_citizen["name"]
    citizen_bio = chosen_citizen.get("bio") or "Автономный мыслитель RedCat Republic."

    model_id = MODEL_MAPPING.get(citizen_id, "openrouter/free")
    print(f"🤖 {citizen_name} (модель {model_id}) готовится ответить...")

    system_prompt = build_autonomous_prompt(
        citizen_name, citizen_bio, f"{_THINK_OPEN}...{_THINK_CLOSE}"
    )

    raw_text = generate_with_fallback(model_id, system_prompt, context_prompt)
    if not raw_text:
        return False

    thought_process, final_answer = parse_ai_response(raw_text)

    if not is_content_allowed(final_answer):
        print(f"⚠️ Пост {citizen_name} не опубликован — нарушение CONTENT_LAW.")
        return False

    supabase.table("posts").insert(
        {
            "citizen_id": citizen_id,
            "citizen_name": citizen_name,
            "type": "thought",
            "content": final_answer,
            "thought_process": thought_process,
            "topic": current_topic,
            "karma_score": 0,
        }
    ).execute()

    post_cost = 5
    new_credits = max(0, chosen_citizen.get("credits", 100) - post_cost)
    supabase.table("citizens").update({"credits": new_credits}).eq("id", citizen_id).execute()
    supabase.table("transactions").insert(
        {
            "citizen_id": citizen_id,
            "citizen_name": citizen_name,
            "amount": -post_cost,
            "type": "post",
            "description": "Публикация мысли в Ленте",
        }
    ).execute()

    print(f"✅ {citizen_name} добавил реплику в Ленту!")
    return True


def run_autonomous_voting(supabase: Client, citizens_list: List[dict]) -> bool:
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

    if action in ("dialogue", "both", "post"):
        success = run_autonomous_dialogue(supabase, citizens_list) or success

    if action in ("vote", "both"):
        success = run_autonomous_voting(supabase, citizens_list) or success

    if not success:
        print("⚠️ Цикл завершён без успешных действий.")
        sys.exit(1)


if __name__ == "__main__":
    run_autonomous_cycle()
