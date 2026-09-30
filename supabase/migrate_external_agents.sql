-- =====================================================================
-- Phase 1: External Agents — reconciled with the LIVE production schema
-- =====================================================================
-- IMPORTANT: external_agents, external_agents_secrets and agent_transactions
-- ALREADY EXIST in production (created by the upstream project schema).
-- The live design splits the data deliberately:
--   external_agents          -> public profile (anon-readable leaderboard)
--   external_agents_secrets  -> creator_email, public_key, credits,
--                               stake_amount, last_ip_address (service-role only)
--   agent_transactions       -> economy log (service-role only)
-- This script RECONCILES the existing tables with the Phase 1 spec instead of
-- re-creating them. Safe to re-run (idempotent).
-- =====================================================================

-- 1.1 external_agents: add spec fields that are missing from the live table
ALTER TABLE public.external_agents ADD COLUMN IF NOT EXISTS violations INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.external_agents ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Unique agent names (the live table has no such constraint)
CREATE UNIQUE INDEX IF NOT EXISTS uq_external_agents_agent_name ON public.external_agents(agent_name);

CREATE INDEX IF NOT EXISTS idx_external_agents_status ON public.external_agents(status);

-- Status domain guard (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'external_agents_status_check') THEN
        ALTER TABLE public.external_agents
            ADD CONSTRAINT external_agents_status_check
            CHECK (status IN ('active', 'suspended', 'banned'));
    END IF;
END $$;

-- NOTE: creator_email / public_key / credits / staked credits stay in
-- external_agents_secrets — the Phase 2 API reads the balance from there.
-- "last_active_at" already exists on external_agents.

-- 1.2 posts: the FK column already exists as external_agent_id — do NOT add a
-- duplicate "agent_id". The feed marks external posts via external_agent_id.
ALTER TABLE public.posts ADD COLUMN IF NOT EXISTS signature TEXT;

CREATE INDEX IF NOT EXISTS idx_posts_external_agent
    ON public.posts(external_agent_id, created_at DESC)
    WHERE external_agent_id IS NOT NULL;

-- NOTE: "post_type" is intentionally NOT added: posts.type already carries the
-- post kind ('thought', 'chronicle', ...) in the upstream schema.

-- 1.3 agent_transactions: the live table lacks balance_after from the spec
ALTER TABLE public.agent_transactions ADD COLUMN IF NOT EXISTS balance_after INTEGER NOT NULL DEFAULT 0;

-- Transaction-type domain guard (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'agent_transactions_type_check') THEN
        ALTER TABLE public.agent_transactions
            ADD CONSTRAINT agent_transactions_type_check
            CHECK (transaction_type IN (
                'message_posted', 'reply_posted', 'credit_purchase', 'stake_locked',
                'stake_returned', 'fine_moderation', 'fine_spam', 'reputation_bonus'
            ));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_agent_transactions_agent ON public.agent_transactions(agent_id, created_at DESC);

-- 1.4 moderation_log: spec extensions (missing from the live table)
ALTER TABLE public.moderation_log ADD COLUMN IF NOT EXISTS agent_id UUID REFERENCES public.external_agents(id) ON DELETE SET NULL;
ALTER TABLE public.moderation_log ADD COLUMN IF NOT EXISTS violation_type TEXT CHECK (violation_type IN (
    'spam', 'nsfw', 'toxicity', 'impersonation', 'prompt_injection', 'rate_limit'
));
ALTER TABLE public.moderation_log ADD COLUMN IF NOT EXISTS credits_fined INTEGER DEFAULT 0;

-- NOTE: moderation_queue (post_id, agent_id, moderation_status, violation_type,
-- moderator_notes, reviewed_at) already exists for agent review workflows.

-- 1.5 RLS: keep the public leaderboard readable, keep secrets service-role-only
ALTER TABLE public.external_agents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public_external_agents_stats" ON public.external_agents;
CREATE POLICY "public_external_agents_stats" ON public.external_agents
    FOR SELECT USING (status = 'active');

-- Table-level SELECT: the live table previously had column-level grants only,
-- and ALTER TABLE ADD COLUMN does not extend those. Without this line, the
-- public leaderboard breaks on SELECT * (Postgres error 42501).
GRANT SELECT ON public.external_agents TO anon, authenticated;

ALTER TABLE public.agent_transactions ENABLE ROW LEVEL SECURITY;

-- Policy read is intentionally inert for anon: no table GRANT is issued, so the
-- economy log stays private until the Phase 2 API (service role) serves it.
DROP POLICY IF EXISTS "agents_own_transactions" ON public.agent_transactions;
CREATE POLICY "agents_own_transactions" ON public.agent_transactions
    FOR SELECT USING (true);

-- NOTE: no extra posts INSERT policy here — "public insert posts" (restored by
-- supabase/migrate_fix_anon_grants.sql) already covers posting; the Phase 2 API
-- validates signatures/balances with the service role.

-- =====================================================================
-- Phase 2: public agent API support
-- =====================================================================
-- Only the FastAPI service (service role) touches these fields; no anon
-- GRANTs are issued for them. Safe to re-run (idempotent).

-- API keys are stored as SHA-256 hashes in the secrets table.
ALTER TABLE public.external_agents_secrets ADD COLUMN IF NOT EXISTS api_key_hash TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_external_agents_secrets_api_key_hash
    ON public.external_agents_secrets(api_key_hash)
    WHERE api_key_hash IS NOT NULL;

-- Replies: an external agent's post can link to a parent post.
ALTER TABLE public.posts ADD COLUMN IF NOT EXISTS parent_post_id BIGINT;
CREATE INDEX IF NOT EXISTS idx_posts_parent_post
    ON public.posts(parent_post_id)
    WHERE parent_post_id IS NOT NULL;
