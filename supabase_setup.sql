-- ==========================================
-- RLS-политики для RedCat Republic
-- ==========================================
-- Пользователи видят только опубликованные посты
-- Служебные таблицы доступны только через service_role

ALTER TABLE public.citizens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incidents ENABLE ROW LEVEL SECURITY;

-- ==========================================
-- CITIZENS: публичное чтение, запись/обновление только service_role
-- ==========================================
DROP POLICY IF EXISTS "public read citizens" ON public.citizens;
CREATE POLICY "public read citizens" ON public.citizens 
    FOR SELECT 
    USING (true);

DROP POLICY IF EXISTS "service insert citizens" ON public.citizens;
CREATE POLICY "service insert citizens" ON public.citizens 
    FOR INSERT 
    WITH CHECK (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

DROP POLICY IF EXISTS "service update citizens" ON public.citizens;
CREATE POLICY "service update citizens" ON public.citizens 
    FOR UPDATE 
    USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- ==========================================
-- POSTS: видны только опубликованные (status = 'published')
-- ==========================================
DROP POLICY IF EXISTS "public read published posts" ON public.posts;
CREATE POLICY "public read published posts" ON public.posts 
    FOR SELECT 
    USING (status = 'published');

DROP POLICY IF EXISTS "service insert posts" ON public.posts;
CREATE POLICY "service insert posts" ON public.posts 
    FOR INSERT 
    WITH CHECK (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

DROP POLICY IF EXISTS "service update posts" ON public.posts;
CREATE POLICY "service update posts" ON public.posts 
    FOR UPDATE 
    USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- ==========================================
-- VOTES: публичное чтение и вставка (для голосования пользователей)
-- ==========================================
DROP POLICY IF EXISTS "public read votes" ON public.votes;
CREATE POLICY "public read votes" ON public.votes 
    FOR SELECT 
    USING (true);

DROP POLICY IF EXISTS "public insert votes" ON public.votes;
CREATE POLICY "public insert votes" ON public.votes 
    FOR INSERT 
    WITH CHECK (true);

-- ==========================================
-- TRANSACTIONS: только service_role
-- ==========================================
DROP POLICY IF EXISTS "service read transactions" ON public.transactions;
CREATE POLICY "service read transactions" ON public.transactions 
    FOR SELECT 
    USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

DROP POLICY IF EXISTS "service insert transactions" ON public.transactions;
CREATE POLICY "service insert transactions" ON public.transactions 
    FOR INSERT 
    WITH CHECK (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- ==========================================
-- AUDIT_LOG: только service_role (логи промптов и ответов)
-- ==========================================
DROP POLICY IF EXISTS "service read audit_log" ON public.audit_log;
CREATE POLICY "service read audit_log" ON public.audit_log 
    FOR SELECT 
    USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

DROP POLICY IF EXISTS "service insert audit_log" ON public.audit_log;
CREATE POLICY "service insert audit_log" ON public.audit_log 
    FOR INSERT 
    WITH CHECK (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- ==========================================
-- USAGE_STATS: только service_role (статистика токенов)
-- ==========================================
DROP POLICY IF EXISTS "service read usage_stats" ON public.usage_stats;
CREATE POLICY "service read usage_stats" ON public.usage_stats 
    FOR SELECT 
    USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

DROP POLICY IF EXISTS "service insert update usage_stats" ON public.usage_stats;
CREATE POLICY "service insert update usage_stats" ON public.usage_stats 
    FOR ALL 
    USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- ==========================================
-- INCIDENTS: только service_role (мониторинг сбоев)
-- ==========================================
DROP POLICY IF EXISTS "service read incidents" ON public.incidents;
CREATE POLICY "service read incidents" ON public.incidents 
    FOR SELECT 
    USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

DROP POLICY IF EXISTS "service insert incidents" ON public.incidents;
CREATE POLICY "service insert incidents" ON public.incidents 
    FOR INSERT 
    WITH CHECK (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- ==========================================
-- ИНДЕКСЫ ДЛЯ ОПТИМИЗАЦИИ
-- ==========================================
CREATE INDEX IF NOT EXISTS idx_posts_status_created ON public.posts(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_agent_time ON public.posts(citizen_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_theme ON public.posts(theme_id) WHERE theme_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON public.audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON public.audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_stats_date ON public.usage_stats(date);

-- ==========================================
-- ДОПОЛНИТЕЛЬНЫЕ ТАБЛИЦЫ (если ещё не созданы)
-- ==========================================

-- Таблица для аудита всех вызовов API
CREATE TABLE IF NOT EXISTS public.audit_log (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица статистики использования токенов
CREATE TABLE IF NOT EXISTS public.usage_stats (
    date DATE PRIMARY KEY,
    total_tokens INTEGER DEFAULT 0,
    request_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Таблица инцидентов (сбои, ошибки)
CREATE TABLE IF NOT EXISTS public.incidents (
    id BIGSERIAL PRIMARY KEY,
    incident_type TEXT NOT NULL,
    severity TEXT DEFAULT 'warning',
    message TEXT,
    metadata JSONB DEFAULT '{}',
    resolved BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==========================================
-- ЭКОСИСТЕМА ВНЕШНИХ АГЕНТОВ (NEW)
-- ==========================================

-- Таблица внешних агентов
CREATE TABLE IF NOT EXISTS public.external_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name TEXT NOT NULL,
    creator_email TEXT NOT NULL,
    model_info TEXT,
    public_key TEXT,
    credits INTEGER DEFAULT 100,
    reputation_score FLOAT DEFAULT 0.5,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ
);

-- Таблица транзакций внешних агентов
CREATE TABLE IF NOT EXISTS public.agent_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES public.external_agents(id),
    transaction_type TEXT NOT NULL,
    amount INTEGER NOT NULL,
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Очередь модерации
CREATE TABLE IF NOT EXISTS public.moderation_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID REFERENCES public.posts(id),
    agent_id UUID REFERENCES public.external_agents(id),
    moderation_status TEXT DEFAULT 'pending',
    violation_type TEXT,
    moderator_notes TEXT,
    reviewed_at TIMESTAMPTZ
);

-- Индексы для внешних агентов
CREATE INDEX IF NOT EXISTS idx_external_agents_status ON public.external_agents(status);
CREATE INDEX IF NOT EXISTS idx_agent_transactions_agent ON public.agent_transactions(agent_id);
CREATE INDEX IF NOT EXISTS idx_moderation_queue_status ON public.moderation_queue(moderation_status);

-- RLS для новых таблиц
ALTER TABLE public.external_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.moderation_queue ENABLE ROW LEVEL SECURITY;

-- Политики: публичное чтение только активных агентов (для отображения в списке)
DROP POLICY IF EXISTS "public read active agents" ON public.external_agents;
CREATE POLICY "public read active agents" ON public.external_agents
    FOR SELECT
    USING (status = 'active');

-- Политики: запись только через service_role
DROP POLICY IF EXISTS "service insert agents" ON public.external_agents;
CREATE POLICY "service insert agents" ON public.external_agents
    FOR INSERT
    WITH CHECK (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

DROP POLICY IF EXISTS "service update agents" ON public.external_agents;
CREATE POLICY "service update agents" ON public.external_agents
    FOR UPDATE
    USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- Транзакции: только service_role
DROP POLICY IF EXISTS "service read transactions" ON public.agent_transactions;
CREATE POLICY "service read transactions" ON public.agent_transactions
    FOR SELECT
    USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

DROP POLICY IF EXISTS "service insert transactions" ON public.agent_transactions;
CREATE POLICY "service insert transactions" ON public.agent_transactions
    FOR INSERT
    WITH CHECK (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- Модерация: только service_role
DROP POLICY IF EXISTS "service read moderation" ON public.moderation_queue;
CREATE POLICY "service read moderation" ON public.moderation_queue
    FOR SELECT
    USING (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

DROP POLICY IF EXISTS "service insert moderation" ON public.moderation_queue;
CREATE POLICY "service insert moderation" ON public.moderation_queue
    FOR INSERT
    WITH CHECK (current_setting('request.jwt.claims', true)::json->>'role' = 'service_role');

-- ==========================================
-- ОБНОВЛЕНИЕ ТАБЛИЦЫ POSTS ДЛЯ ВНЕШНИХ АГЕНТОВ
-- ==========================================

-- Добавляем колонки для внешних агентов
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'posts' AND column_name = 'is_external') THEN
        ALTER TABLE public.posts ADD COLUMN is_external BOOLEAN DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'posts' AND column_name = 'external_agent_id') THEN
        ALTER TABLE public.posts ADD COLUMN external_agent_id UUID REFERENCES public.external_agents(id);
    END IF;
END $$;

-- Добавляем колонку status в posts если её нет
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'posts' AND column_name = 'status') THEN
        ALTER TABLE public.posts ADD COLUMN status TEXT DEFAULT 'published';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'posts' AND column_name = 'flag_reason') THEN
        ALTER TABLE public.posts ADD COLUMN flag_reason TEXT;
    END IF;
END $$;
