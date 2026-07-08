-- Judge review of a run's trace: code-reviewer-style findings that tag specific
-- agent steps (evidence) with an axis/severity and a suggested improvement.
-- Available for any run, not just failures.
-- Apply by pasting into the Supabase SQL editor, or:
--   psql "$DATABASE_URL" -f migrations/0005_run_review.sql

begin;

-- { summary, reviewed_at, findings: [{ steps:[int], axis, severity, title, recommendation }] }
alter table sandbox_runs add column if not exists review jsonb not null default '{}'::jsonb;

commit;
