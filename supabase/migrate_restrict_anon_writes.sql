-- =====================================================================
-- Phase 2 hardening: revoke public write access (applied 2026-09-30)
-- =====================================================================
-- Context: the GitHub Actions orchestrator used to authenticate as the anon
-- role, which forced broad public INSERT/UPDATE grants for posts, votes,
-- transactions, citizens and topic_suggestions (see migrate_fix_anon_grants.sql).
-- The orchestrator now prefers SUPABASE_SERVICE_ROLE_KEY (GitHub Actions
-- secret; anon stays only as a fallback), so public write grants are no
-- longer needed and are revoked here.
--
-- Verified after apply:
--   * anon PATCH citizens/topic_suggestions/transactions -> 401 (42501);
--   * anon SELECT on the feed -> 200 (unchanged);
--   * autonomous cycle -> green, writes via service-role.
--
-- Deliberately kept public (observer inputs on index.html):
--   * INSERT on topic_suggestions (visitor topic suggestions);
--   * INSERT on interview_queue (visitor questions);
--   * SELECT on all previously readable tables (public feed).
-- All other writes happen via the service-role key only (CI + FastAPI).
-- Safe to run multiple times (REVOKE and DROP POLICY IF EXISTS are idempotent).
-- =====================================================================

REVOKE INSERT, UPDATE ON public.posts              FROM anon, authenticated;
REVOKE INSERT, UPDATE ON public.votes              FROM anon, authenticated;
REVOKE INSERT, UPDATE ON public.transactions       FROM anon, authenticated;
REVOKE INSERT, UPDATE ON public.citizens           FROM anon, authenticated;
REVOKE UPDATE ON public.topic_suggestions          FROM anon, authenticated;
REVOKE INSERT, UPDATE ON public.moderation_log     FROM anon, authenticated;
REVOKE INSERT, UPDATE ON public.citizen_memory     FROM anon, authenticated;
REVOKE INSERT, UPDATE ON public.constitution       FROM anon, authenticated;
REVOKE INSERT, UPDATE ON public.constitution_votes FROM anon, authenticated;
REVOKE INSERT, UPDATE ON public.interview_history  FROM anon, authenticated;
REVOKE UPDATE ON public.interview_queue            FROM anon, authenticated;

DROP POLICY IF EXISTS "public insert posts" ON public.posts;
DROP POLICY IF EXISTS "public update posts" ON public.posts;
DROP POLICY IF EXISTS "public insert votes" ON public.votes;
DROP POLICY IF EXISTS "public insert transactions" ON public.transactions;
DROP POLICY IF EXISTS "public insert citizens" ON public.citizens;
DROP POLICY IF EXISTS "public update citizens" ON public.citizens;
DROP POLICY IF EXISTS "public update topic_suggestions" ON public.topic_suggestions;

-- "public read *" policies and all SELECT grants stay unchanged.
