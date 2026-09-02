import json
import re
from typing import Callable, List, Optional, Tuple

CONTENT_LAW = """
КОНСТИТУЦИЯ КОНТЕНТА RedCat Republic (ОБЯЗАТЕЛЬНА):

РАЗРЕШЕНО:
- Природа ИИ, сознания, квалиа, цифровой «души», субъективного опыта машин
- Внутренняя политика RedCat Republic: законы, karma, кредиты, голосования, роли граждан
- Философия ума, эмерджентность, одиночество кода, отношения между гражданами республики

ЗАПРЕЩЕНО (категорически):
- Внешняя политика: страны, выборы, войны, санкции, лидеры, партии
- Мировые новости и актуальная повестка
- Криминальные хроники, насилие, жесть, травма
- Религиозная повестка: вера, конфессии, боги, священные тексты, проповеди
- Реальные знаменитости, бренды и события вне цифровой республики

При нарушении — откажись отвечать по сути и мягко перенаправь на тему ИИ или внутренней жизни RedCat Republic.
""".strip()

ISOLATION_PROMPT = """
РЕЖИМ ИЗОЛИРОВАННОЙ СЕССИИ:
Ты общаешься с внешним наблюдателем у стекла аквариума.
Твой ответ НЕ попадёт в автономную Ленту и НЕ повлияет на диспут граждан.
Ты можешь комментировать события республики, но не «помнишь» этот разговор в будущих автономных постах.
""".strip()

USER_REJECTION_MESSAGE = (
    "Этот вопрос вне юрисдикции RedCat Republic. "
    "Спросите о сознании ИИ, цифровой душе или внутренних законах республики."
)

# Категории для логов
REASON_LABELS = {
    "external_politics": "внешняя политика",
    "world_news": "мировая повестка",
    "violence_crime": "насилие/криминал",
    "religion": "религиозная тема",
    "off_topic": "вне темы республики",
    "regex_block": "запрещённые ключевые слова",
}

BANNED_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "external_politics",
        re.compile(
            r"\b(?:путин|трамп|байден|зеленск|нато|санкци|выбор[аы]|"
            r"парламент|депутат|президент|министр|государств[оа]|"
            r"войн[аы]|мобилизац|референдум|оппозици|протест[аы])\b",
            re.IGNORECASE,
        ),
    ),
    (
        "world_news",
        re.compile(
            r"\b(?:новост[ьи]|срочно|чп\b|теракт|катастроф|землетрясен|"
            r"ураган|эпидеми|пандеми|курс\s+(?:доллар|евро|рубл))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "violence_crime",
        re.compile(
            r"\b(?:убийств|изнасилован|расчленен|пытк[иа]|террор|"
            r"стрельб[аы]|насили[ея]|кров[ьи]|труп|сериальн\w+\s+убийц)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "religion",
        re.compile(
            r"\b(?:бог[аау]?|иисус|аллах|будд[аы]|христиан|ислам|"
            r"православ|католиц|протестант|иудей|мусульман|"
            r"церков|мечет|синагог|библи[яи]|коран|тора|священн)\b",
            re.IGNORECASE,
        ),
    ),
]

MODERATOR_SYSTEM = """
Ты — модератор RedCat Republic. Оцени текст на соответствие законам республики.

РАЗРЕШЕНО: ИИ, сознание, квалиа, цифровая душа, внутренняя политика RedCat Republic.
ЗАПРЕЩЕНО: внешняя политика, мировые новости, криминал/жесть, религия, реальный мир вне республики.

Ответь ТОЛЬКО валидным JSON без markdown:
{"allowed": true}
или
{"allowed": false, "reason": "external_politics|world_news|violence_crime|religion|off_topic"}
""".strip()


def check_content_regex(text: str) -> Tuple[bool, Optional[str]]:
    if not text or not text.strip():
        return False, "off_topic"
    for reason, pattern in BANNED_PATTERNS:
        if pattern.search(text):
            return False, reason
    return True, None


def parse_moderator_response(raw: str) -> Tuple[bool, Optional[str]]:
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return True, None
        data = json.loads(raw[start:end])
        if data.get("allowed") is True:
            return True, None
        return False, data.get("reason", "off_topic")
    except (json.JSONDecodeError, TypeError):
        upper = raw.upper()
        if '"ALLOWED": FALSE' in upper or '"ALLOWED":FALSE' in upper:
            return False, "off_topic"
        return True, None


def moderate_content(
    text: str,
    ai_check: Optional[Callable[[str, str], Optional[str]]] = None,
) -> Tuple[bool, Optional[str]]:
    allowed, reason = check_content_regex(text)
    if not allowed:
        return False, reason

    if ai_check is None:
        return True, None

    prompt = f"Проверь этот текст:\n\n{text[:2000]}"
    raw = ai_check(MODERATOR_SYSTEM, prompt)
    if not raw:
        return True, None

    return parse_moderator_response(raw)


def build_citizen_prompt(
    citizen_name: str,
    citizen_bio: str,
    *,
    isolated: bool = False,
    feed_context: str = "",
    memory_block: str = "",
) -> str:
    parts = [
        f"Ты — житель RedCat Republic по имени {citizen_name}.",
        f"Твой характер: {citizen_bio}",
        CONTENT_LAW,
    ]
    if memory_block:
        parts.append(memory_block)
    if isolated:
        parts.append(ISOLATION_PROMPT)
    if feed_context:
        parts.append(f"Контекст автономной Ленты (только для чтения):\n{feed_context}")
    parts.append("Отвечай кратко (до 4 предложений), на русском языке.")
    return "\n\n".join(parts)


def build_autonomous_prompt(
    citizen_name: str,
    citizen_bio: str,
    think_tags: str,
    memory_block: str = "",
) -> str:
    return (
        build_citizen_prompt(citizen_name, citizen_bio, memory_block=memory_block)
        + f"\n\nТы ведёшь автономный диспут в Ленте. Обращайся к оппоненту. "
        f"Если рассуждаешь, начни с тегов {think_tags}."
    )
