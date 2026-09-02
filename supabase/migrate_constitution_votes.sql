-- RedCat 3.0 phase 2: deduplicated constitution votes
-- Supabase → SQL Editor → Run once

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
