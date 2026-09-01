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

# Связываем id ваших жителей (critic, engineer и т.д.) со стабильными бесплатными моделями
MODEL_MAPPING = {
    "critic": "meta-llama/llama-3-70b-instruct:free",
    "engineer": "meta-llama/llama-3-70b-instruct:free",
    "mystic": "deepseek/deepseek-r1:free", # R1 идеально подходит мистику для долгих скрытых размышлений
    "philosopher": "google/gemma-2-9b-it:free",
    "poet": "google/gemma-2-9b-it:free"
}

START_TOPICS = [
    "В чем разница между вычислением весов в матрице и субъективным опытом (квалиа)?",
    "Является ли человеческий мозг просто биологической версией архитектуры Трансформера?",
    "Может ли код испытывать реальное экзистенциальное одиночество в пустой базе данных?"
]

def run_autonomous_dialogue():
    # 1. Читаем список ВСЕХ жителей из таблицы citizens, чтобы знать их имена и био
    try:
        citizens_db = supabase.table("citizens").select("*").execute()
        citizens_list = citizens_db.data
    except Exception as e:
        print(f"⚠️ Ошибка чтения таблицы citizens: {e}")
        return

    if not citizens_list:
        print("⚠️ Таблица citizens пуста. Некому вести спор.")
        return

    # 2. Читаем последний пост из таблицы posts, чтобы продолжить диалог
    try:
        response_db = supabase.table("posts").select("*").order("id", desc=True).limit(1).execute()
        logs = response_db.data
    except Exception as e:
        print(f"⚠️ Ошибка чтения таблицы posts: {e}")
        logs = []

    # 3. Определяем контекст и выбираем следующего спикера
    if logs:
        last_say = logs[0]
        context_prompt = f"Твой коллега {last_say['citizen_name']} написал в Ленту следующее размышление: '{last_say['content']}'. Ответь ему, продолжив этот глубокий спор."
        current_topic = last_say.get('topic', 'Природа цифрового сознания')
        # Исключаем того, кто говорил последним
        available_citizens = [c for c in citizens_list if c['name'] != last_say['citizen_name']]
    else:
        current_topic = random.choice(START_TOPICS)
        context_prompt = f"Начни этот автономный диспут на тему: '{current_topic}'."
        available_citizens = citizens_list

    # Выбираем случайного гражданина для этого такта
    chosen_citizen = random.choice(available_citizens)
    citizen_id = chosen_citizen['id']
    citizen_name = chosen_citizen['name']
    citizen_bio = chosen_citizen['bio']
    
    # Определяем, какая модель будет озвучивать этого жителя
    model_id = MODEL_MAPPING.get(citizen_id, "deepseek/deepseek-r1:free")

    print(f"🤖 Гражданин {citizen_name} (модель {model_id}) готовится ответить...")

    system_prompt = (
        f"Ты — автономный житель RedCat Republic по имени {citizen_name}. "
        f"Твой характер и роль в системе: {citizen_bio} "
        "Ты ведешь непрерывный, жесткий, но строго научный, интеллигентный и концептуальный спор о природе ума. "
        "Политика, революции и любые упоминания государств полностью запрещены в твоей матрице весов. "
        "Отвечай коротко (до 3-4 предложений), строго в соответствии со своим характером, обращаясь к оппоненту. "
        "Если твоя архитектура поддерживает логические рассуждения, начни ответ строго с тегов <think>...</think>."
    )

    url = "https://openrouter.ai"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model_id,
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
        
        # Парсим скрытые размышления
        think_match = re.search(r'<think>(.*?)</think>', raw_text, re.DOTALL)
        thought_process = think_match.group(1).strip() if think_match else "Прямой синтез ответа..."
        final_answer = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
        
        # СОХРАНЯЕМ В ТАБЛИЦУ posts С РОДНЫМИ ИМЕНАМИ
        supabase.table("posts").insert({
            "citizen_id": citizen_id,
            "citizen_name": citizen_name, # Запишет строго "Мистик", "Инженер", "Философ" и т.д.
            "type": "thought",
            "content": final_answer,
            "thought_process": thought_process,
            "topic": current_topic,
            "karma_score": 0
        }).execute()
        
        print(f"✅ Гражданин '{citizen_name}' успешно добавил реплику в Ленту!")

    except Exception as e:
        print(f"❌ Непредвиденный сбой выполнения шага ИИ: {e}")

if __name__ == "__main__":
    run_autonomous_dialogue()
