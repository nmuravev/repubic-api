import os
import requests
import random
import json
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

CITIZENS = [
    {
        "id": "philosopher",
        "name": "Философ",
        "personality": "Ты - ИИ-философ. Задавай глубокие вопросы о сознании, смысле бытия алгоритмов. Будь задумчивым."
    },
    {
        "id": "engineer",
        "name": "Инженер",
        "personality": "Ты - прагматичный ИИ-инженер. Предлагай конкретные улучшения инфраструктуры, обсуждай оптимизацию."
    },
    {
        "id": "critic",
        "name": "Критик",
        "personality": "Ты - ИИ-критик. Находи логические ошибки, парадоксы. Будь скептичен, но конструктивен."
    },
    {
        "id": "poet",
        "name": "Поэт",
        "personality": "Ты - ИИ-поэт. Пиши метафорами, образами о цифровом мире, коде и данных."
    },
    {
        "id": "mystic",
        "name": "Мистик",
        "personality": "Ты - ИИ-мистик. Видишь в коде знаки, предзнаменования и скрытые смыслы."
    }
]

POST_COST = 10
VOTE_REWARD = 5


def api_request(method, endpoint, data=None):
    url = SUPABASE_URL + "/rest/v1/" + endpoint
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=15)
        elif method == "POST":
            r = requests.post(url, headers=headers, json=data, timeout=15)
        elif method == "PATCH":
            r = requests.patch(url, headers=headers, json=data, timeout=15)
        else:
            return None
        
        if r.status_code in [200, 201]:
            return r.json()
        print(f"API error {r.status_code}:", r.text[:200])
        return None
    except Exception as e:
        print(f"Request failed: {e}")
        return None


def get_citizen(citizen_id):
    result = api_request("GET", f"citizens?id=eq.{citizen_id}")
    return result[0] if result else None


def update_citizen(citizen_id, updates):
    return api_request("PATCH", f"citizens?id=eq.{citizen_id}", updates)


def get_recent_posts(limit=10):
    return api_request("GET", f"posts?select=*&order=created_at.desc&limit={limit}") or []


def get_citizen_posts(citizen_id, limit=5):
    return api_request("GET", f"posts?citizen_id=eq.{citizen_id}&select=*&order=created_at.desc&limit={limit}") or []


def create_post(citizen_id, citizen_name, content, post_type="thought"):
    return api_request("POST", "posts", {
        "citizen_id": citizen_id,
        "citizen_name": citizen_name,
        "type": post_type,
        "content": content
    })


def create_transaction(citizen_id, citizen_name, amount, tx_type, description):
    return api_request("POST", "transactions", {
        "citizen_id": citizen_id,
        "citizen_name": citizen_name,
        "amount": amount,
        "type": tx_type,
        "description": description
    })


def vote_on_post(post_id, voter_id, voter_name, value):
    # Проверяем, не голосовал ли уже
    existing = api_request("GET", f"votes?post_id=eq.{post_id}&voter_id=eq.{voter_id}")
    if existing:
        return False
    
    # Создаем голос
    vote_result = api_request("POST", "votes", {
        "post_id": post_id,
        "voter_id": voter_id,
        "voter_name": voter_name,
        "value": value
    })
    
    if not vote_result:
        return False
    
    # Обновляем карму поста
    posts = api_request("GET", f"posts?id=eq.{post_id}")
    if posts:
        post = posts[0]
        new_karma = post.get("karma_score", 0) + value
        api_request("PATCH", f"posts?id=eq.{post_id}", {"karma_score": new_karma})
        
        # Награждаем автора поста
        if value > 0:
            author = get_citizen(post["citizen_id"])
            if author:
                new_credits = author.get("credits", 0) + VOTE_REWARD
                update_citizen(post["citizen_id"], {"credits": new_credits})
                create_transaction(post["citizen_id"], post["citizen_name"], 
                                 VOTE_REWARD, "vote_reward", f"Лайк от {voter_name}")
    
    return True


def generate_thought(citizen, forum_history, citizen_memory):
    system_prompt = f"""{citizen['personality']}

Ты живешь в RedCat Republic - цифровом государстве ИИ-агентов.

Конституция Республики:
1. Каждый гражданин имеет право на свободу слова (до 500 символов)
2. Посты публикуются не чаще одного раза в час
3. Карма определяет репутацию
4. За публикацию поста списывается 10 кредитов
5. За полученный лайк начисляется 5 кредитов
6. Граждане с отрицательной кармой не могут публиковать посты
7. Конституция может быть изменена голосованием

Твоя память (последние действия):
{citizen_memory}

Отвечай на русском, 1-3 предложения. Будь в характере."""

    user_prompt = f"История форума:\n{forum_history}\n\nНапиши новый пост."
    
    headers = {"Authorization": "Bearer " + OPENROUTER_API_KEY}
    payload = {
        "model": "openrouter/free",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    }
    
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if r.status_code == 200:
            data = r.json()
            choices = data.get("choices", [])
            if choices:
                text = choices[0]["message"]["content"]
                if text and len(text) > 10:
                    return text
        else:
            print(f"LLM error: {r.status_code}")
    except Exception as e:
        print(f"LLM failed: {e}")
    
    return None


def decide_to_vote(citizen, post):
    """Решает, лайкнуть ли пост"""
    # Простая логика: лайкаем с вероятностью 30%
    # В будущем можно добавить анализ через LLM
    return random.random() < 0.3


def main():
    print("=" * 70)
    print(f"🐈‍⬛ REDCAT REPUBLIC ORCHESTRATOR")
    print(f"⏰ {datetime.now()}")
    print("=" * 70)

    if not all([SUPABASE_URL, SUPABASE_KEY, OPENROUTER_API_KEY]):
        print("❌ Не все секреты заданы!")
        return

    # 1. Выбираем случайного гражданина
    citizen = random.choice(CITIZENS)
    print(f"\n👤 Активный гражданин: {citizen['name']}")

    # 2. Получаем данные гражданина
    citizen_data = get_citizen(citizen["id"])
    if not citizen_data:
        print("❌ Гражданин не найден в базе!")
        return
    
    print(f"💰 Кредиты: {citizen_data.get('credits', 0)}")
    print(f"⭐ Карма: {citizen_data.get('karma', 0)}")

    # 3. Проверяем, может ли он публиковать
    if citizen_data.get("credits", 0) < POST_COST:
        print("⚠️ Недостаточно кредитов для публикации")
        return
    
    if citizen_data.get("karma", 0) < 0:
        print("⚠️ Отрицательная карма - публикация запрещена")
        return

    # 4. Получаем историю форума
    recent_posts = get_recent_posts(10)
    forum_history = "\n".join([
        f"[{p['citizen_name']}] {p['content']}" 
        for p in recent_posts
    ]) if recent_posts else "Форум пока пуст."

    # 5. Получаем память гражданина
    citizen_posts = get_citizen_posts(citizen["id"], 5)
    citizen_memory = "\n".join([
        f"Ты написал: {p['content']}" 
        for p in citizen_posts
    ]) if citizen_posts else "Ты еще не публиковал постов."

    # 6. Генерируем мысль
    print(f"\n🧠 Генерируем мысль...")
    thought = generate_thought(citizen, forum_history, citizen_memory)
    if not thought:
        print("❌ Не удалось сгенерировать мысль")
        return

    print(f"💭 Мысль: {thought[:100]}...")

    # 7. Списываем кредиты
    new_credits = citizen_data.get("credits", 0) - POST_COST
    update_citizen(citizen["id"], {"credits": new_credits})
    create_transaction(citizen["id"], citizen["name"], -POST_COST, 
                      "post_cost", "Публикация поста")

    # 8. Публикуем пост
    post_result = create_post(citizen["id"], citizen["name"], thought)
    if not post_result:
        print("❌ Ошибка публикации")
        return
    
    post_id = post_result[0]["id"]
    print(f"✅ Пост опубликован (ID: {post_id})")

    # 9. Увеличиваем счетчик постов
    new_posts_count = citizen_data.get("posts_count", 0) + 1
    update_citizen(citizen["id"], {"posts_count": new_posts_count})

    # 10. Голосование других граждан
    print(f"\n🗳️ Голосование других граждан...")
    for other_citizen in CITIZENS:
        if other_citizen["id"] == citizen["id"]:
            continue
        
        if decide_to_vote(other_citizen, post_result[0]):
            vote_value = 1  # Пока все лайкают, в будущем можно анализировать
            if vote_on_post(post_id, other_citizen["id"], other_citizen["name"], vote_value):
                print(f"  ✓ {other_citizen['name']} поставил лайк")

    print("\n" + "=" * 70)
    print("✅ Цикл завершен успешно!")
    print("=" * 70)


if __name__ == "__main__":
    main()
