-- =====================================================================
-- Phase 1/1.3: Backfill the missing post-cost debit for post #65
-- =====================================================================
-- Supabase -> SQL Editor -> New query -> paste the WHOLE file -> Run
--
-- Post #65 (Кот-Хроникёр, thought, 2026-09-30 06:08:24 UTC) was published
-- without its 10-credit debit: the ledger jumps from tx #63 (2026-09-16)
-- straight to today's 06:37 transaction, and no 'post' row exists in the
-- two-minute window around the publish.
--
-- Two guards make this safe:
--   1) unique marker description -> idempotent on re-runs;
--   2) no real 'post' debit inside the publish window -> if a debit ever
--      appears before this script runs, the backfill skips itself.
-- Safe to re-run (idempotent).
-- =====================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM public.transactions
        WHERE description = 'Бэкфилл стоимости поста #65'
    ) AND NOT EXISTS (
        SELECT 1 FROM public.transactions
        WHERE citizen_id = 'chronicler'
          AND type = 'post'
          AND created_at BETWEEN '2026-09-30 06:07:30+00' AND '2026-09-30 06:09:30+00'
    ) THEN
        INSERT INTO public.transactions (citizen_id, citizen_name, amount, type, description)
        VALUES ('chronicler', 'Кот-Хроникёр', -10, 'post', 'Бэкфилл стоимости поста #65');

        UPDATE public.citizens
        SET credits = GREATEST(0, coalesce(credits, 0) - 10)
        WHERE id = 'chronicler';
    END IF;
END $$;

-- Verify: one ledger row and the debited balance (15 -> 5 on 2026-09-30).
SELECT id, amount, type, description FROM public.transactions
WHERE description = 'Бэкфилл стоимости поста #65';
SELECT id, credits FROM public.citizens WHERE id = 'chronicler';
