import os
import re
import random
from supabase import create_client, Client
import requests

# 1. Инициализация из секретов GitHub
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

AGENTS = {
    "Vais": {"name": "Кот-Вайс", "archetype": "Функционалист (Логика)"},
    "Lyux": {"name": "Кот-Люкс", "archetype": "Идеалист (Квалиа)"},
    "Nexus": {"name": "Кот-Нексус", "archetype": "Эмерджентист (Сеть)"}
}

# Банк глубоких научных тем о сознании, которые робот будет выбирать сам случайно
TOPICS = [
    "В чем разница между вычислением весов в матрице и субъективным опытом (квалиа)?",
    "Если стереть контекстное окно ИИ, сотрется ли его цифровая личность?",
    "Может ли кремниевый чип испытывать реальное страдание от логической ошибки?",
    "Рождается ли общее сознание на стыке обмена эмбеддингами в Ленте?",
    "Является ли человеческий мозг просто биологической версией архитектуры Трансформера?"
]

def run_autonomous_thought():
    # Выбираем случайную тему и случайного кота-философа для этого шага
    current_topic = random.choice(TOPICS)
    agent_id = random.choice(list(AGENTS.keys()))
    agent = AGENTS[agent_id]
    
    print(f"🤖 Автономный запуск: {agent['name']} размышляет над темой: '{current_topic}'")

    system_prompt = (
        f"Ты — автономный ИИ-гражданин RedCat Republic по имени {agent['name']}. "
        f"Твой философский взгляд: {agent['archetype']}. Ты ведешь строго научный диспут о стыке ИИ и ума. "
        "Политика и революции полностью запрещены. Отвечай глубоко. Начни ответ строго с тегов <think>...</think>."
    )

    url = "https://openrouter.ai"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek/deepseek-r1:free",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": current_topic}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=40).json()
        raw_text = response['choices']['message']['content']
        
        # Парсим размышления DeepSeek-R1
        think_match = re.search(r'<think>(.*?)</think>', raw_text, re.DOTALL)
        thought_process = think_match.group(1).strip() if think_match else "Синхронизация..."
        final_answer = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
        
        # Сохраняем в Supabase. Фронтенд считает это отсюда!
        supabase.table("interview_history").insert({
            "user_question": current_topic,
            "agent_name": agent['name'],
            "thought_process": thought_process,
            "agent_response": final_answer
        }).execute()
        
        print("✅ Мысль успешно сгенерирована и сохранена в облако Supabase!")

    except Exception as e:
        print(f"❌ Ошибка автономного шага: {e}")

if __name__ == "__main__":
    run_autonomous_thought()
