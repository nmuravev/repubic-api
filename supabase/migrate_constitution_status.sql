-- =====================================================================
-- Phase 1/1.1: Constitution lifecycle status — voting / passed / rejected
-- =====================================================================
-- Supabase -> SQL Editor -> New query -> paste the WHOLE file -> Run
--
-- Why: articles id=10 and id=11 (0 for, 6 against) were rejected by vote,
-- but nothing ever marked them as decided. run_constitution_proposal()
-- counted every is_active=false row as "pending" and refused new proposals
-- once two were stuck — a permanent deadlock.
--
-- This migration adds an explicit lifecycle column:
--   'voting'   -> open for votes; counts against the pending limit (max 2)
--   'passed'   -> adopted (is_active = true)
--   'rejected' -> closed after a full vote without adoption; does NOT block
--
-- Safe to re-run (idempotent).
-- =====================================================================

ALTER TABLE public.constitution ADD COLUMN IF NOT EXISTS status text DEFAULT 'voting';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'constitution_status_check') THEN
        ALTER TABLE public.constitution
            ADD CONSTRAINT constitution_status_check
            CHECK (status IN ('voting', 'passed', 'rejected'));
    END IF;
END $$;

-- Backfill: adopted articles are 'passed'; fully-voted failures are 'rejected'.
UPDATE public.constitution SET status = 'passed'
WHERE is_active = true AND status = 'voting';

UPDATE public.constitution SET status = 'rejected'
WHERE is_active = false
  AND status = 'voting'
  AND coalesce(votes_for, 0) + coalesce(votes_against, 0) >= (SELECT count(*) FROM public.citizens);

-- Keep the new column readable with the existing public read policy
-- (ALTER TABLE ADD COLUMN does not extend column-level GRANTs).
GRANT SELECT ON public.constitution TO anon, authenticated;

-- Verify: rows 10/11 -> 'rejected', adopted articles -> 'passed',
-- and no row may remain with (is_active = false AND status = 'voting').
SELECT id, article_number, status, is_active, votes_for, votes_against
FROM public.constitution ORDER BY id;
