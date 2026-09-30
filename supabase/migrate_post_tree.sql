-- =====================================================================
-- Phase 2: Debate tree — foreign key on posts.parent_post_id
-- =====================================================================
-- Supabase -> SQL Editor -> New query -> paste the WHOLE file -> Run
--
-- posts.parent_post_id (BIGINT, added in migrate_external_agents.sql)
-- has no referential integrity: a reply can point at a missing post, and
-- deleting a parent leaves its replies dangling. This migration:
--   1) nulls out orphan parent references (defensive; prod had none),
--   2) adds a self-referencing FK with ON DELETE CASCADE, so deleting a
--      post also deletes its whole reply subtree,
--   3) keeps the partial index idx_posts_parent_post for tree queries.
--
-- Note: CASCADE removes reply rows only. Votes / citizen_memory rows that
-- reference a deleted reply must still be cleaned by the deleting script
-- (same pattern as migrate_cleanup_leaked_posts.sql).
--
-- Safe to re-run (idempotent).
-- =====================================================================

-- 1) Clear orphan references so the FK can be validated.
UPDATE public.posts
SET parent_post_id = NULL
WHERE parent_post_id IS NOT NULL
  AND parent_post_id NOT IN (SELECT id FROM public.posts);

-- 2) Self-referencing FK: deleting a post deletes its reply subtree.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'posts_parent_post_id_fkey'
    ) THEN
        ALTER TABLE public.posts
            ADD CONSTRAINT posts_parent_post_id_fkey
            FOREIGN KEY (parent_post_id) REFERENCES public.posts(id)
            ON DELETE CASCADE;
    END IF;
END $$;

-- 3) Partial index for tree queries (no-op if migrate_external_agents.sql ran).
CREATE INDEX IF NOT EXISTS idx_posts_parent_post
    ON public.posts(parent_post_id)
    WHERE parent_post_id IS NOT NULL;

-- Verify: expect one row with confdeltype = 'c' (cascade) and 0 orphans.
SELECT conname, confdeltype FROM pg_constraint
WHERE conname = 'posts_parent_post_id_fkey';

SELECT count(*) AS orphan_replies
FROM public.posts p
WHERE p.parent_post_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM public.posts q WHERE q.id = p.parent_post_id);
