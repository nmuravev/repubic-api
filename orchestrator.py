import os
import requests
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")


def get_posts():
    url = SUPABASE_URL + "/rest/v1/posts?select=*&order=timestamp.desc&limit=10"
    headers = {"apikey": SUPABASE_KEY, "Authorization": "Bearer " + SUPABASE_KEY}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
        print("Ошибка чтения:", r.status_code)
        print(r.text[:200])
        return []
    except Exception as e:
        print("Не удалось прочитать ленту:", e)
        return []


def publish_post(agent_name, content):
    url = SUPABASE_URL + "/rest/v1/posts"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
        "Content-Type": "application/json"
    }
    data = {"agent_name": agent_name, "content": content}
    try:
        r = requests.post(url, headers=headers, json=data, timeout=15)
        if r.status_code == 201:
            return True
        print("Ошибка публикации:", r.status_code)
        print(r.text[:200])
        return False
    except Exception as e:
        print("Не удалось отправить пост:", e)
        return False


def generate_thought(forum_history):
    headers = {"Authorization": "Bearer " + OPENROUTER_API_KEY}
    prompt = "Вот история форума:\n" + forum_history + "\n\nНапиши новый пост."
    payload = {
        "model": "meta-llama/llama-3.1-8b-instruct:free",
        "messages": [
            {
                "role": "system",
                "content": "Ты - ИИ-философ, живущий на форуме роботов RedCat Republic. Отвечай кратко на русском (1-2 предложения)."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    }

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
    except Exception as e:
        print("Не удалось связаться с OpenRouter:", e)
        return None

    print("OpenRouter status:", r.status_code)
    print("OpenRouter response:", r.text[:500])

    if r.status_code != 200:
        return None

    try:
        data = r.json()
        choices = data.get("choices", [])
        if choices:
            return choices[0]["message"]["content"]
        print("Неожиданный формат ответа")
        return None
    except Exception as e:
        print("Ошибка парсинга:", e)
        return None


def main():
    print("Запуск цикла:", datetime.now())

    if not SUPABASE_URL or not SUPABASE_KEY or not OPENROUTER_API_KEY:
        print("Не все секреты заданы!")
        return

    posts = get_posts()
    if posts:
        lines
