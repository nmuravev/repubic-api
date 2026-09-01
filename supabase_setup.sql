-- Выполните в Supabase SQL Editor для автономной работы через anon key.
-- RLS должен разрешать чтение/запись для публичного фронтенда и GitHub Actions.

ALTER TABLE public.citizens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;
-- Фаза 1: session_id для приватных интервью
ALTER TABLE public.interview_history ADD COLUMN IF NOT EXISTS session_id text;
CREATE INDEX IF NOT EXISTS idx_interview_session ON public.interview_history(session_id);


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
