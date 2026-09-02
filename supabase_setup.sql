-- ═══════════════════════════════════════════════════════════════════
-- RedCat Republic — настройка Supabase
-- ═══════════════════════════════════════════════════════════════════
-- ⚠️  Этот файл запускается в SQL Editor (НЕ импорт CSV).
--     Данные граждан импортируйте из supabase/csv/citizens.csv
--     через Table Editor → citizens → Import CSV.
--     Подробная инструкция: supabase/SUPABASE_SETUP_RU.md
-- ═══════════════════════════════════════════════════════════════════

ALTER TABLE public.citizens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.constitution ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.interview_history ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.interview_history ADD COLUMN IF NOT EXISTS session_id text;
CREATE INDEX IF NOT EXISTS idx_interview_session ON public.interview_history(session_id);

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

DROP POLICY IF EXISTS "public read citizens" ON public.citizens;
CREATE POLICY "public read citizens" ON public.citizens FOR SELECT USING (true);

DROP POLICY IF EXISTS "public read posts" ON public.posts;
CREATE POLICY "public read posts" ON public.posts FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert posts" ON public.posts;
CREATE POLICY "public insert posts" ON public.posts FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "public update posts" ON public.posts;
CREATE POLICY "public update posts" ON public.posts FOR UPDATE USING (true);

DROP POLICY IF EXISTS "public read votes" ON public.votes;
CREATE POLICY "public read votes" ON public.votes FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert votes" ON public.votes;
CREATE POLICY "public insert votes" ON public.votes FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "public read transactions" ON public.transactions;
CREATE POLICY "public read transactions" ON public.transactions FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert transactions" ON public.transactions;
CREATE POLICY "public insert transactions" ON public.transactions FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "public read interview_history" ON public.interview_history;
CREATE POLICY "public read interview_history" ON public.interview_history FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert interview_history" ON public.interview_history;
CREATE POLICY "public insert interview_history" ON public.interview_history FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "public insert citizens" ON public.citizens;
CREATE POLICY "public insert citizens" ON public.citizens FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "public update citizens" ON public.citizens;
CREATE POLICY "public update citizens" ON public.citizens FOR UPDATE USING (true);

DROP POLICY IF EXISTS "public read constitution" ON public.constitution;
CREATE POLICY "public read constitution" ON public.constitution FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert constitution" ON public.constitution;
CREATE POLICY "public insert constitution" ON public.constitution FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "public update constitution" ON public.constitution;
CREATE POLICY "public update constitution" ON public.constitution FOR UPDATE USING (true);

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

-- Realtime (включите также в Dashboard → Database → Replication для posts и interview_history)
ALTER PUBLICATION supabase_realtime ADD TABLE public.posts;
ALTER PUBLICATION supabase_realtime ADD TABLE public.interview_history;
