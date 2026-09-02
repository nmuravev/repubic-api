-- RedCat 3.0 phase 3: moderation audit log + citizen counters
-- Supabase → SQL Editor → Run once

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
CREATE INDEX IF NOT EXISTS idx_moderation_log_allowed ON public.moderation_log(allowed);

ALTER TABLE public.moderation_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read moderation_log" ON public.moderation_log;
CREATE POLICY "public read moderation_log" ON public.moderation_log FOR SELECT USING (true);

DROP POLICY IF EXISTS "public insert moderation_log" ON public.moderation_log;
CREATE POLICY "public insert moderation_log" ON public.moderation_log FOR INSERT WITH CHECK (true);
