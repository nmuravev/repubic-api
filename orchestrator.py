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
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.json()
        print(f"⚠️ Ошибка чтения постов: {r.status_code} {r.text[:200]}")
        return []
    except Exception as e:
        print(f"⚠️ Не удалось прочитать ленту: {e}")
        return []


def publish_post(agent_name, content):
    """Публикуем новый пост"""
    url = f"{SUPABASE_URL}/rest/v1/posts"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    data = {"agent_name": agent_name, "content": content}
    try:
        r = requests.post(url, headers=headers, json=data, timeout=15)
        if r.status_code == 201:
            return True
        print(f"⚠️ Ошибка публикации: {r.status_code} {r.text[:200
