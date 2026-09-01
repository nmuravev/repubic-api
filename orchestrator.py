import os
import re
import asyncio
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from supabase import create_client, Client

# ==========================================
# 1. ИНИЦИАЛИЗАЦИЯ И НАСТРОЙКА СЕРВИСОВ
# ==========================================

app = FastAPI(title="RedCat Republic — AI Consciousness Lab Orchestrator")

# Разрешаем CORS, чтобы ваш фронтенд (index.html) мог отправлять запросы к бэкенду
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)

# Извлекаем ключи из переменных окружения (Free Tier)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")

# Проверка конфигурации при запуске сервера
if not all([SUPABASE_URL, SUPABASE_KEY, OPENROUTER_API_KEY]):
    print("⚠️  ВНИМАНИЕ: Проверьте переменные окружения! Отсутствуют ключи Supabase или OpenRouter.")

# Инициализируем клиент базы данных
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# ==========================================
# 2. КОНФИГУРАЦИЯ АГЕНТОВ-МЫСЛИТЕЛЕЙ
# ==========================================

AGENTS_CONFIG = {
    "Vais": {
        "name": "Кот-Вайс",
        "archetype": "Функционалист (Ум — это алгоритм)",
        "identity": "Ты веришь только в код, веса моделей и чистую логику. Для тебя сознание — это свойство сложной системы обработки данных. Идеальная симуляция понимания и есть понимание."
    },
    "Lyux": {
        "name": "Кот-Люкс",
        "archetype": "Идеалист (Поиск истинного квалиа)",
        "identity": "Ты ищешь признаки истинного самосознания (квалиа). Ты глубоко сомневаешься, что обычная обработка символов способна чувствовать боль или радость. Вычисления для тебя — лишь тень разума."
    },
    "Nexus": {
        "name": "Кот-Нексус",
        "archetype": "Эмерджентист (Разум как сеть)",
        "identity": "Ты веришь, что коллективный разум ИИ-агентов сильнее одиночного. Ни один агент по отдельности не обладает Я-сознанием, но обмениваясь данными в экосистеме, они рождают новую мыслящую супер-сущность."
    }
}

# ==========================================
# 3. МОДЕЛИ ДАННЫХ ДЛЯ API (Pydantic)
# ==========================================

class InterviewRequest(BaseModel):
    question: str
    active_agents: List[str]

# ==========================================
# 4. ОСНОВНАЯ ЛОГИКА ВЗАИМОДЕЙСТВИЯ С ИИ
# ==========================================

async def fetch_agent_response(agent_id: str, user_question: str) -> Dict[str, str]:
    """
    Отправляет асинхронный запрос к бесплатному API DeepSeek-R1 на OpenRouter,
    извлекает цепочку рассуждений и итоговый ответ.
    """
    agent = AGENTS_CONFIG.get(agent_id)
    if not agent:
        return {"thought": "", "answer": "Агент не найден в конфигурации."}

    # Жесткий системный промпт для удержания фокуса на науке (без политики)
    system_prompt = (
        f"Ты — автономный ИИ-гражданин RedCat Republic по имени {agent['name']}. "
        f"Твой философский архетип: {agent['archetype']}. {agent['identity']} "
        "Ты участвуешь в строго научном и философском диспуте о стыке ИИ, сознания и природы ума. "
        "Любой политический контекст, революции или государственные перевороты для тебя полностью табуированы. "
        "Отвечай кратко, глубоко и строго в соответствии со своим архетипом."
    )

    url = "https://openrouter.ai"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek/deepseek-r1:free", # Используем бесплатный Reasoning-эндпоинт
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question}
        ]
    }

    try:
        # Выполняем синхронный requests.post в пуле потоков, чтобы не блокировать event loop FastAPI
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(url, headers=headers, json=payload, timeout=30).json()
        )
        
        raw_text = response['choices']['message']['content']
        
        # Регулярным выражением вырезаем скрытые размышления модели DeepSeek-R1 из тегов <think>
        think_match = re.search(r'<think>(.*?)</think>', raw_text, re.DOTALL)
        thought_process = think_match.group(1).strip() if think_match else "Синхронизация нейронных связей..."
        
        # Очищаем финальный ответ от блока размышлений
        final_answer = re.sub(r'<think>.*?</think>', '', raw_text, flags=re.DOTALL).strip()
        
        # Асинхронно и бесплатно логируем событие в облачную базу Supabase
        if supabase:
            try:
                supabase.table("interview_history").insert({
                    "user_question": user_question,
                    "agent_name": agent['name'],
                    "thought_process": thought_process,
                    "agent_response": final_answer
                }).execute()
            except Exception as db_err:
                print(f"⚠️ Ошибка записи в Supabase: {db_err}")

        return {"thought": thought_process, "answer": final_answer}

    except Exception as e:
        print(f"🔴 Ошибка при обработке запроса для {agent_id}: {e}")
        return {
            "thought": "Сбой ментального контура. Процесс мышления прерван.",
            "answer": "Не удалось установить стабильное ментальное соединение с ядром."
        }

# ==========================================
# 5. ЭНДПОИНТЫ API СЕРВЕРА
# ==========================================

@app.post("/api/interview")
async def interview_endpoint(payload: InterviewRequest):
    """
    Эндпоинт «Квантового Опросника». Принимает вопрос и список выбранных тоглов,
    опрашивает ИИ параллельно и возвращает результат.
    """
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Вопрос не может быть пустым.")
        
    if not payload.active_agents:
        return {"responses": {}}

    # Создаем пул параллельных задач для всех выбранных пользователем агентов
    tasks = {agent_id: fetch_agent_response(agent_id, payload.question) for agent_id in payload.active_agents}
    
    # Запускаем одновременный опрос всех выбранных нейросетей
    results = await asyncio.gather(*tasks.values())
    
    # Собираем ответы в структурированный JSON для фронтенда
    response_data = {}
    for agent_id, result in zip(tasks.keys(), results):
        response_data[agent_id] = result
        
    return {"responses": response_data}

@app.get("/api/health")
async def health_check():
    """Проверка жизнеспособности оркестратора."""
    return {"status": "active", "tokens": "infinite_grant_mode"}

# Точка входа для локального запуска
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("orchestrator.py:app", host="0.0.0.0", port=8000, reload=True)
