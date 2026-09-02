-- RedCat Republic 3.0 — таблица персональной памяти котов
-- Supabase → SQL Editor → Run (после citizens)

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
