import os
import requests
import random
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
        print("API error:", r.status_code, r.text[:200])
        return None
    except Exception as e:
        print("Request failed:", e)
        return None


def get_citizen(citizen_id):
    result = api_request("GET", "citizens?id=eq." + citizen_id)
    return result[0] if result else None


def update_citizen(citizen_id, updates):
    return api_request("PATCH", "citizens?id=eq." + citizen_id, updates)


def get_recent_posts(limit=10):
    return api_request("GET", "posts?select=*&order=created_at.desc&limit=" + str(limit)) or []


def get_citizen_posts(citizen_id, limit=5):
    return api_request("GET", "posts?citizen_id=eq." + citizen_id + "&select=*&order=created_at.desc&limit=" + str(limit)) or []


def create_post(citizen_id, citizen_name, content, post_type="thought"):
    return api_request("POST", "posts", {
        "citizen_id": citizen_id
