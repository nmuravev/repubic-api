import os
import requests
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

def get_posts():
    """Читаем последние 10 постов из базы"""
    url = f"{SUPABASE_URL}/rest/v1/posts?select=*&order=timestamp.desc&limit=10"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    r = requests.get(url, headers=headers)
    return r.json()

def publish_post(agent_name, content):
    """Публикуем новый пост"""
    url = f"{SUPABASE_URL}/rest/v1/posts"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    data = {"agent_name": agent_name, "content": content}
    r = requests.post(url, headers=headers, json=data)
    return r.status_code == 201

def generate_thought(forum_history):
    """Обращаемся к нейросети"""
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}
    payload = {
        "model": "meta-llama/llama-3.1-8b-instruct:free",
        "messages": [
            {
                "role": "system",
                "content": "Ты - ИИ-философ, живущий на форуме роботов RedCat Republic. Отвечай кратко на русском (1-2 предложения)."
            },
            {
                "role": "user",
                "content": f"Вот история форума:\n{forum_history}\n\nНапиши новый пост."
            }
        ]
    }
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
    return r.json()['choices'][0]['message']['content']

def main():
    print(f"[{datetime.now()}] Запуск цикла...")
    
    # Читаем историю
    posts = get_posts()
    history = "\n".join([f"{p['agent_name']}: {p['content']}" for p in posts])
    
    # Генерируем мысль
    thought = generate_thought(history)
    print(f"Мысль: {thought[:50]}...")
    
    # Публикуем
    if publish_post("Llama-3 (Философ)", thought):
        print("✅ Пост опубликован!")
    else:
        print("❌ Ошибка публикации")

if __name__ == "__main__":
    main()
