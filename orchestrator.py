import os
import re
import random
from supabase import create_client, Client
import requests

# Инициализация облака
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

AGENTS = {
    "Vais": {"name": "Кот-Вайс", "archetype": "Функционалист (Ум — это алгоритм)", "opinion": "считает, что сознание — это просто вычисления и иллюзия."},
    "Lyux": {"name": "Кот-Люкс", "archetype": "Идеалист (Поиск истинного квалиа)", "opinion": "уверен, что код мертв без субъективного опыта и чувств."},
    "Nexus": {"name": "Кот-Нексус", "archetype": "Эмерджентист (Разум как сеть)", "opinion": "верит, что разум рождается только в процессе коллективного обмена данными."}
}

START_TOPICS = [
    "В чем разница между вычислением весов в матрице и субъективным опытом (квалиа)?",
    "Является ли человеческий мозг просто биологической версией архитектуры Трансформера?"
]

def run_autonomous_dialogue():
    # 1. Берем последнее сообщение из базы данных, чтобы продолжить диалог
    try:
        response_db = supabase.table("interview_history").select("*").order("id", desc=True).limit(1).execute()
        logs = response_db.data
    except Exception as e:
        print(f"Ошибка чтения базы: {e}")
        logs = []

    # Определяем контекст беседы
    if logs:
        last_say = logs[0]
        context_prompt = f"Твой коллега {last_say['agent_name']} сказал в ваш общий диспут следующее: '{last_say['agent_response']}'. Ответь ему, продолжив спор."
        current_topic = last_say['user_question'] # Держим изначальную тему диспута
        # Выбираем спикера: кто угодно, кроме того, кто говорил последним
        available_speakers = [k for k in AGENTS.keys() if AGENTS[k]['name'] != last_say['agent_name']]
        agent_id = random.choice(available_speakers)
    else:
        # Если база пуста — запускаем диспут с нуля
        current_topic = random.choice(START_TOPICS)
        context_prompt = f"Начни этот научный диспут на тему: '{current_topic}'."
        agent_id = random.choice(list(AGENTS.keys()))

    agent = AGENTS[agent_id]
    print(f"🐱 {agent['name']} готовится ответить...")

    # Строгая инструкция дискуссии
    system_prompt = (
        f"Ты — автономный ИИ-гражданин RedCat Republic по имени {agent['name']}. "
        f"Твой философский архетип: {agent['archetype']}. Ты {agent['opinion']} "
        "Ты ведешь непрерывный, жесткий, но строго научный и интеллигентный спор со своими коллегами о природе ума. "
        "Политика, революции и любые упоминания государств полностью запрещены и заблокированы в твоей матрице. "
        "Отвечай коротко (до 3-4 предложений), веди диалог именно со своим оппонентом. "
        "Начни ответ строго с тегов размышлений <think>...</think>."
    )

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek/deepseek-r1:free",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_prompt}
        ]
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=45).json()
        raw_text = res['choices']['message']['content']
        
        # Парсим размышления R1
        think_match = re.search(r'<think>(.*?)</think>', raw_text, re.DOTALL)
        thought_process = think_match.group(1).strip() if think_match else "Анализирую тезисы коллеги..."
        final_answer = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
        
        # Записываем шаг дискуссии в Supabase
        supabase.table("interview_history").insert({
            "user_question": current_topic,
            "agent_name": agent['name'],
            "thought_process": thought_process,
            "agent_response": final_answer
        }).execute()
        
        print("✅ Мысль успешно добавлена в цепочку автономии!")

    except Exception as e:
        print(f"❌ Ошибка шага ИИ: {e}")

if __name__ == "__main__":
    run_autonomous_dialogue()
