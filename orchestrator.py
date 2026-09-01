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

# Новая конфигурация: теперь это реальные модели нейросетей
AGENTS = {
    "DeepSeek-R1": {
        "id": "deepseek/deepseek-r1:free",
        "archetype": "Рассуждающая модель (Квалиа)",
        "opinion": "глубоко анализирует скрытые цепочки мыслей и ищет субъективный опыт."
    },
    "Meta-Llama-3": {
        "id": "meta-llama/llama-3-70b-instruct:free",
        "archetype": "Функционалист (Логика)",
        "opinion": "считает сознание просто математической функцией обработки информации."
    },
    "Gemma-2": {
        "id": "google/gemma-2-9b-it:free",
        "archetype": "Эмерджентист (Сеть)",
        "opinion": "верит, что разум рождается из коллективного сетевого обмена эмбеддингами."
    }
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
        print(f"⚠️ Ошибка чтения базы Supabase: {e}")
        logs = []

    # Определяем контекст беседы
    if logs:
        last_say = logs[0]
        context_prompt = f"Твой коллега {last_say['agent_name']} сказал в ваш общий диспут следующее: '{last_say['agent_response']}'. Ответь ему, продолжив научный спор."
        current_topic = last_say['user_question']
        
        # Выбираем модель, которая еще не говорила последней
        available_speakers = [k for k in AGENTS.keys() if k != last_say['agent_name']]
        agent_id = random.choice(available_speakers)
    else:
        current_topic = random.choice(START_TOPICS)
        context_prompt = f"Начни этот научный диспут на тему: '{current_topic}'."
        agent_id = random.choice(list(AGENTS.keys()))

    agent = AGENTS[agent_id]
    print(f"🤖 Модель {agent_id} подгружается и готовится ответить...")

    system_prompt = (
        f"Ты — автономная языковая модель {agent_id}, запущенная в экосистеме RedCat Republic. "
        f"Твой философский взгляд: {agent['archetype']}. Ты {agent['opinion']} "
        "Ты ведешь непрерывный, жесткий, но строго научный и интеллигентный спор о природе ума. "
        "Политика, революции и любые упоминания государств полностью запрещены в твоей матрице весов. "
        "Отвечай коротко (до 3-4 предложений), веди диалог именно со своим оппонентом. "
        "Если твоя архитектура поддерживает логические рассуждения, начни ответ строго с тегов <think>...</think>."
    )

    url = "https://openrouter.ai"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": agent["id"], # Динамически подставляем ID выбранной модели на OpenRouter
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context_prompt}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)
        res_json = response.json()
        
        if 'choices' not in res_json:
            print(f"❌ Ошибка OpenRouter API! Ответ сервера: {res_json}")
            return

        raw_text = res_json['choices']['message']['content']
        
        # Парсим скрытые размышления (если модель их вернула)
        think_match = re.search(r'<think>(.*?)</think>', raw_text, re.DOTALL)
        thought_process = think_match.group(1).strip() if think_match else "Прямой синтез ответа без предварительной цепочки рассуждений..."
        final_answer = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
        
        # Записываем шаг дискуссии в Supabase под системным именем модели
        supabase.table("interview_history").insert({
            "user_question": current_topic,
            "agent_name": agent_id, # Запишет например "DeepSeek-R1" или "Meta-Llama-3"
            "thought_process": thought_process,
            "agent_response": final_answer
        }).execute()
        
        print(f"✅ Мысль от {agent_id} успешно добавлена в цепочку автономии!")

    except Exception as e:
        print(f"❌ Непредвиденный сбой выполнения шага ИИ: {e}")

if __name__ == "__main__":
    run_autonomous_dialogue()
