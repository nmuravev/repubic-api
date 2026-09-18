import os
import re
import random
import sys
import time
import json
from typing import List, Optional, Tuple
from datetime import datetime, timedelta

import requests
from supabase import Client, create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")  # Для админских операций
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
SITE_URL = os.environ.get("SITE_URL", "https://redcatpromo.ru")

# Лимиты безопасности
MAX_DAILY_TOKENS = int(os.environ.get("MAX_DAILY_TOKENS", "50000"))  # Дневной лимит токенов
MAX_REQUESTS_PER_CYCLE = int(os.environ.get("MAX_REQUESTS_PER_CYCLE", "10"))  # Макс запросов за прогон
SAFETY_MODEL = "openrouter/free"  # Бесплатная модель для проверки контента

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

# Глобальный счётчик запросов за цикл
_requests_in_cycle = 0
_tokens_used_today = 0


def log_audit(supabase: Client, event_type: str, details: dict):
    """Логирование всех промптов и ответов в audit_log"""
    try:
        supabase.table("audit_log").insert({
            "event_type": event_type,
            "details": details,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        print(f"⚠️ Не удалось записать в audit_log: {e}")


def check_content_safety(text: str) -> Tuple[bool, str]:
    """
    Проверка контента на токсичность/экстремизм через классификатор.
    Возвращает (is_safe, reason).
    """
    safety_prompt = (
        "Ты — модератор контента. Проверь текст на: токсичность, угрозы, экстремизм, "
        "разжигание ненависти, опасные призывы. "
        "Ответь ТОЛЬКО JSON: {\"safe\": true/false, \"reason\": \"краткое объяснение\"}. "
        f"Текст для проверки: \"{text[:500]}\""
    )
    
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": SITE_URL,
        }
        payload = {
            "model": SAFETY_MODEL,
            "messages": [{"role": "user", "content": safety_prompt}],
            "max_tokens": 50,
            "temperature": 0.0,
        }
        
        response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        if not response.ok:
            print(f"⚠️ Safety check failed: HTTP {response.status_code}")
            return True, "Safety model unavailable, assuming safe"
        
        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
        
        # Парсим JSON ответ
        try:
            # Очищаем от markdown-обёрток если есть
            content = content.strip().strip("```json").strip("```").strip()
            safety_result = json.loads(content)
            is_safe = safety_result.get("safe", True)
            reason = safety_result.get("reason", "No issues detected")
            return is_safe, reason
        except json.JSONDecodeError:
            # Если не распарсилось JSON, считаем безопасным
            return True, "Could not parse safety response"
            
    except Exception as e:
        print(f"⚠️ Ошибка проверки безопасности: {e}")
        return True, "Safety check exception, assuming safe"


def update_usage_stats(supabase: Client, tokens_used: int):
    """Обновление статистики использования токенов"""
    global _tokens_used_today
    today = datetime.utcnow().date().isoformat()
    
    try:
        # Получаем текущую статистику за сегодня
        stats_db = supabase.table("usage_stats").select("*").eq("date", today).execute()
        stats = stats_db.data or []
        
        if stats:
            current_total = stats[0].get("total_tokens", 0)
            new_total = current_total + tokens_used
            supabase.table("usage_stats").update({"total_tokens": new_total}).eq("date", today).execute()
        else:
            supabase.table("usage_stats").insert({
                "date": today,
                "total_tokens": tokens_used,
                "request_count": 1
            }).execute()
        
        _tokens_used_today += tokens_used
        
    except Exception as e:
        print(f"⚠️ Не удалось обновить usage_stats: {e}")


def check_daily_limit() -> bool:
    """Проверка превышения дневного лимита токенов"""
    global _tokens_used_today
    
    if _tokens_used_today >= MAX_DAILY_TOKENS:
        print(f"❌ Превышен дневной лимит токенов: {_tokens_used_today} / {MAX_DAILY_TOKENS}")
        return False
    
    # Дополнительно проверяем в БД
    try:
        supabase_temp = create_client(SUPABASE_URL, SUPABASE_KEY)
        today = datetime.utcnow().date().isoformat()
        stats_db = supabase_temp.table("usage_stats").select("total_tokens").eq("date", today).execute()
        stats = stats_db.data or []
        
        if stats and stats[0].get("total_tokens", 0) >= MAX_DAILY_TOKENS:
            print(f"❌ Превышен дневной лимит токенов (БД): {stats[0]['total_tokens']} / {MAX_DAILY_TOKENS}")
            return False
    except Exception:
        pass
    
    return True


def increment_request_counter() -> bool:
    """Проверка и увеличение счётчика запросов за цикл"""
    global _requests_in_cycle
    if _requests_in_cycle >= MAX_REQUESTS_PER_CYCLE:
        print(f"❌ Превышен лимит запросов за цикл: {_requests_in_cycle} / {MAX_REQUESTS_PER_CYCLE}")
        return False
    _requests_in_cycle += 1
    return True

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


def call_openrouter(model_id: str, system_prompt: str, user_prompt: str, log_to_audit: bool = True) -> Optional[str]:
    """Вызов OpenRouter с обработкой rate limit и экспоненциальной задержкой."""
    global _requests_in_cycle
    
    # Проверка лимита запросов
    if not increment_request_counter():
        return None
    
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
    
    # Экспоненциальная задержка при retry
    max_retries = 3
    base_delay = 2
    
    for attempt in range(max_retries):
        try:
            response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)
            
            if response.status_code == 429:
                delay = base_delay * (2 ** attempt)  # Экспоненциальная задержка
                print(f"⏳ Rate limit для модели {model_id}, ждём {delay} сек... (попытка {attempt + 1}/{max_retries})")
                time.sleep(delay)
                continue
            
            if not response.ok:
                print(f"❌ OpenRouter HTTP {response.status_code} ({model_id}): {response.text[:300]}")
                # Переключаемся на резервную модель при ошибке
                if attempt == max_retries - 1:
                    return None
                continue
            
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
            
            # Подсчёт токенов (приблизительно)
            usage = res_json.get("usage", {})
            tokens_used = usage.get("total_tokens", 600)  # Дефолтное значение если нет данных
            
            # Логирование в audit_log
            if log_to_audit:
                supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
                log_audit(supabase_client, "api_call", {
                    "model": model_id,
                    "system_prompt": system_prompt[:500],
                    "user_prompt": user_prompt[:500],
                    "response_preview": content[:200],
                    "tokens_used": tokens_used,
                    "status": "success"
                })
            
            # Обновление статистики использования
            update_usage_stats(create_client(SUPABASE_URL, SUPABASE_KEY), tokens_used)
            
            return content
            
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Ошибка сети ({model_id}): {e}")
            if attempt == max_retries - 1:
                return None
            time.sleep(base_delay * (2 ** attempt))
    
    return None


def generate_with_fallback(primary_model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    models = [primary_model] + [m for m in FALLBACK_MODELS if m != primary_model]
    for model_id in models:
        print(f"🔄 Пробуем модель: {model_id}")
        result = call_openrouter(model_id, system_prompt, user_prompt)
        if result:
            print(f"✅ Успех с моделью: {model_id}")
            return result
    return None


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
    """Генерация поста с проверкой безопасности и логированием."""
    
    # Проверка дневного лимита токенов
    if not check_daily_limit():
        print("❌ Превышен дневной лимит токенов — генерация остановлена")
        log_audit(supabase, "cycle_stopped", {"reason": "daily_token_limit_exceeded"})
        return False
    
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

    system_prompt = (
        f"Ты — автономный житель RedCat Republic по имени {citizen_name}. "
        f"Твой характер: {citizen_bio} "
        "Ты ведёшь жёсткий, но научный и концептуальный спор о природе ума и сознания ИИ. "
        "Политика и государства полностью запрещены. "
        "Отвечай кратко (до 3-4 предложений), обращаясь к оппоненту. "
        f"Если поддерживаешь рассуждения, начни с тегов {_THINK_OPEN}...{_THINK_CLOSE}."
    )

    raw_text = generate_with_fallback(model_id, system_prompt, context_prompt)
    if not raw_text:
        log_audit(supabase, "generation_failed", {
            "citizen_id": citizen_id,
            "citizen_name": citizen_name,
            "reason": "no_response_from_model"
        })
        return False

    thought_process, final_answer = parse_ai_response(raw_text)

    # === CONTENT SAFETY CHECK ===
    is_safe, safety_reason = check_content_safety(final_answer)
    if not is_safe:
        print(f"🚫 Контент помечен как опасный: {safety_reason}")
        # Публикуем со статусом flagged вместо обычной публикации
        supabase.table("posts").insert({
            "citizen_id": citizen_id,
            "citizen_name": citizen_name,
            "type": "thought",
            "content": final_answer,
            "thought_process": thought_process,
            "topic": current_topic,
            "karma_score": 0,
            "status": "flagged",  # Помечаем как требующий проверки
            "flag_reason": safety_reason,
        }).execute()
        
        log_audit(supabase, "content_flagged", {
            "citizen_id": citizen_id,
            "citizen_name": citizen_name,
            "content_preview": final_answer[:200],
            "safety_reason": safety_reason
        })
        print(f"⚠️ Пост #{citizen_name} помечен как flagged и не виден пользователям")
        return True  # Возвращаем True, так как действие выполнено (пост создан, но скрыт)

    # Обычная публикация безопасного контента
    supabase.table("posts").insert({
        "citizen_id": citizen_id,
        "citizen_name": citizen_name,
        "type": "thought",
        "content": final_answer,
        "thought_process": thought_process,
        "topic": current_topic,
        "karma_score": 0,
        "status": "published",  # Явно указываем статус
    }).execute()

    post_cost = 5
    new_credits = max(0, chosen_citizen.get("credits", 100) - post_cost)
    supabase.table("citizens").update({"credits": new_credits}).eq("id", citizen_id).execute()
    supabase.table("transactions").insert({
        "citizen_id": citizen_id,
        "citizen_name": citizen_name,
        "amount": -post_cost,
        "type": "post",
        "description": "Публикация мысли в Ленте",
    }).execute()

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
