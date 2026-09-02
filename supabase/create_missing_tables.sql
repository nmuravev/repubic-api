-- ═══════════════════════════════════════════════════════════════
-- ИСПРАВЛЕНИЕ 404: topic_suggestions и interview_queue
-- ═══════════════════════════════════════════════════════════════
-- Supabase → SQL Editor → New query → вставьте ВЕСЬ этот файл → Run
--
-- Ошибка в браузере:
--   .../rest/v1/topic_suggestions 404
--   .../rest/v1/interview_queue 404
-- означает, что эти таблицы ещё не созданы.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.topic_suggestions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session_id text,
  topic text NOT NULL,
  used boolean DEFAULT false,
  created_at timestamptz DEFAULT timezone('utc'::text, now())
);

CREATE TABLE IF NOT EXISTS public.interview_queue (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session_id text NOT NULL,
  citizen_id text REFERENCES public.citizens(id),
  citizen_name text NOT NULL,
  user_question text NOT NULL,
  status text DEFAULT 'pending',
  created_at timestamptz DEFAULT timezone('utc'::text, now())
);

CREATE INDEX IF NOT EXISTS idx_interview_queue_status ON public.interview_queue(status);
CREATE INDEX IF NOT EXISTS idx_topic_suggestions_used ON public.topic_suggestions(used);

ALTER TABLE public.topic_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interview_queue ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read topic_suggestions" ON public.topic_suggestions;
CREATE POLICY "public read topic_suggestions" ON public.topic_suggestions FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert topic_suggestions" ON public.topic_suggestions;
CREATE POLICY "public insert topic_suggestions" ON public.topic_suggestions FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "public update topic_suggestions" ON public.topic_suggestions;
CREATE POLICY "public update topic_suggestions" ON public.topic_suggestions FOR UPDATE USING (true);

DROP POLICY IF EXISTS "public read interview_queue" ON public.interview_queue;
CREATE POLICY "public read interview_queue" ON public.interview_queue FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert interview_queue" ON public.interview_queue;
CREATE POLICY "public insert interview_queue" ON public.interview_queue FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "public update interview_queue" ON public.interview_queue;
CREATE POLICY "public update interview_queue" ON public.interview_queue FOR UPDATE USING (true);

-- RedCat 3.0: персональная память котов
CREATE TABLE IF NOT EXISTS public.citizen_memory (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  citizen_id text NOT NULL REFERENCES public.citizens(id) ON DELETE CASCADE,
  path text NOT NULL,
  content text NOT NULL,
  source text DEFAULT 'inferred',
  source_post_id bigint,
  updated_at timestamptz DEFAULT timezone('utc'::text, now()),
  UNIQUE (citizen_id, path)
);

CREATE INDEX IF NOT EXISTS idx_citizen_memory_citizen ON public.citizen_memory(citizen_id);
CREATE INDEX IF NOT EXISTS idx_citizen_memory_updated ON public.citizen_memory(updated_at DESC);

ALTER TABLE public.citizen_memory ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read citizen_memory" ON public.citizen_memory;
CREATE POLICY "public read citizen_memory" ON public.citizen_memory FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert citizen_memory" ON public.citizen_memory;
CREATE POLICY "public insert citizen_memory" ON public.citizen_memory FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "public update citizen_memory" ON public.citizen_memory;
CREATE POLICY "public update citizen_memory" ON public.citizen_memory FOR UPDATE USING (true);

-- RedCat 3.0 phase 2: дедуп голосов по конституции
CREATE TABLE IF NOT EXISTS public.constitution_votes (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  article_id bigint NOT NULL REFERENCES public.constitution(id) ON DELETE CASCADE,
  voter_id text NOT NULL REFERENCES public.citizens(id) ON DELETE CASCADE,
  voter_name text NOT NULL,
  vote_for boolean NOT NULL DEFAULT true,
  created_at timestamptz DEFAULT timezone('utc'::text, now()),
  UNIQUE (article_id, voter_id)
);

CREATE INDEX IF NOT EXISTS idx_constitution_votes_article ON public.constitution_votes(article_id);
CREATE INDEX IF NOT EXISTS idx_constitution_votes_voter ON public.constitution_votes(voter_id);

ALTER TABLE public.constitution_votes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read constitution_votes" ON public.constitution_votes;
CREATE POLICY "public read constitution_votes" ON public.constitution_votes FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert constitution_votes" ON public.constitution_votes;
CREATE POLICY "public insert constitution_votes" ON public.constitution_votes FOR INSERT WITH CHECK (true);

-- RedCat 3.0 phase 3: прозрачность модерации
ALTER TABLE public.citizens
  ADD COLUMN IF NOT EXISTS moderation_passed integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS moderation_blocked integer DEFAULT 0;

CREATE TABLE IF NOT EXISTS public.moderation_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at timestamptz DEFAULT timezone('utc'::text, now()),
  source_type text NOT NULL,
  source_id bigint,
  citizen_id text REFERENCES public.citizens(id) ON DELETE SET NULL,
  citizen_name text,
  content_preview text NOT NULL,
  allowed boolean NOT NULL,
  reason text,
  judge_method text NOT NULL DEFAULT 'regex',
  judge_name text DEFAULT 'CONTENT_LAW'
);

CREATE INDEX IF NOT EXISTS idx_moderation_log_created ON public.moderation_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_moderation_log_citizen ON public.moderation_log(citizen_id);

ALTER TABLE public.moderation_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read moderation_log" ON public.moderation_log;
CREATE POLICY "public read moderation_log" ON public.moderation_log FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert moderation_log" ON public.moderation_log;
CREATE POLICY "public insert moderation_log" ON public.moderation_log FOR INSERT WITH CHECK (true);

-- Готово. Обновите redcatpromo.ru (Ctrl+Shift+R) и попробуйте снова.
