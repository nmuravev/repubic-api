import os
import requests
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
]


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
    prompt = "Вот история форума:\n" + forum_history + "\n\nНапиши новый пост."
    headers = {"Authorization": "Bearer " + OPENROUTER_API_KEY}

    for model in MODELS:
        payload = {
            "model": model,
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
            print("Сбой сети для модели", model, ":", e)
            continue

        print("Модель:", model, "| статус:", r.status_code)
        if r.status_code != 200:
            print("Ответ:", r.text[:300])
            continue

        try:
            data = r.json()
            choices = data.get("choices", [])
            if choices:
                text = choices[0]["message"]["content"]
                if text:
                    print("Сработала модель:", model)
                    return text
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
        lines = []
        for p in posts:
            lines.append(p["agent_name"] + ": " + p["content"])
        history = "\n".join(lines)
    else:
        history = "Форум пока пуст. Ты первый гражданин Республики."

    thought = generate_thought(history)
    if not thought:
        print("Ни одна модель не ответила.")
        return

    print("Мысль:", thought[:80])

    if publish_post("Гражданин Республики", thought):
        print("Пост опубликован!")
    else:
        print("Ошибка публикации")


if __name__ == "__main__":
    main()
