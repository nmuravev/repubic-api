-- =====================================================================
-- Phase 0 hotfix: restore anon/authenticated access to posts, votes, transactions
-- =====================================================================
-- Symptom: Postgres error 42501 "permission denied for table posts"
-- (and votes, transactions) from the REST API, blocking:
--   * the GitHub Actions orchestrator (uses SUPABASE_ANON_KEY) from
--     reading the feed and publishing posts;
--   * the public site feed (anon key) from reading posts.
--
-- Root cause: these three tables lost their table-level SQL GRANTs
-- (RLS policies alone are not enough — PostgREST requires the GRANT too).
-- This script re-applies the privileges + policies from supabase_setup.sql.
-- Safe to run multiple times (idempotent).
-- =====================================================================

-- 1. Table privileges
GRANT SELECT, INSERT, UPDATE ON public.posts TO anon, authenticated;
GRANT SELECT, INSERT ON public.votes TO anon, authenticated;
GRANT SELECT, INSERT ON public.transactions TO anon, authenticated;

-- 2. Sequence privileges (required for INSERT into serial-id tables)
GRANT USAGE, SELECT ON SEQUENCE public.posts_id_seq TO anon, authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.votes_id_seq TO anon, authenticated;
GRANT USAGE, SELECT ON SEQUENCE public.transactions_id_seq TO anon, authenticated;

-- 3. Keep RLS enabled and re-assert the public policies
ALTER TABLE public.posts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.votes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.transactions ENABLE ROW LEVEL SECURITY;

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

-- =====================================================================
-- Phase 0 hotfix 2: citizens + topic_suggestions write access
-- =====================================================================
-- Symptom: the 2026-09-30 06:08 UTC autonomous cycle published post #65,
-- then died with 42501 "permission denied for table citizens" on the
-- credits/posts_count UPDATE (publish_post). The vote step also needs
-- UPDATE citizens (karma), and moderation.py counter updates fail too.
--
-- Note: GRANTs cover the table-privilege layer PostgREST checks first;
-- the policies below are inert if RLS is disabled on these tables and
-- required if it is enabled. No ENABLE RLS here on purpose — we do not
-- flip a switch we cannot introspect from the anon key.
-- Safe to run multiple times (idempotent).
-- =====================================================================

GRANT SELECT, INSERT, UPDATE ON public.citizens TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.topic_suggestions TO anon, authenticated;

DO $$
BEGIN
    IF to_regclass('public.topic_suggestions_id_seq') IS NOT NULL THEN
        EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE public.topic_suggestions_id_seq TO anon, authenticated';
    END IF;
END
$$;

DROP POLICY IF EXISTS "public insert citizens" ON public.citizens;
CREATE POLICY "public insert citizens" ON public.citizens FOR INSERT WITH CHECK (true);

DROP POLICY IF EXISTS "public update citizens" ON public.citizens;
CREATE POLICY "public update citizens" ON public.citizens FOR UPDATE USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "public update topic_suggestions" ON public.topic_suggestions;
CREATE POLICY "public update topic_suggestions" ON public.topic_suggestions FOR UPDATE USING (true) WITH CHECK (true);

-- One-off accounting note (commented on purpose — not idempotent, run once
-- manually if you want the ledger to charge for post #65, which was
-- published before the crash reached the credits deduction):
--   UPDATE public.citizens SET credits = GREATEST(0, credits - 10) WHERE id = 'chronicler';
--   INSERT INTO public.transactions (citizen_id, citizen_name, amount, type, description)
--   VALUES ('chronicler', 'Кот-Хроникёр', -10, 'post', 'Публикация (thought) в Ленте');
