-- Data collection for the find-and-fix loop: the trace of the run being fixed,
-- the judge findings that seeded the fix, and the patch Codex generated.
-- Apply by pasting into the Supabase SQL editor, or:
--   psql "$DATABASE_URL" -f migrations/0009_fixes.sql

begin;

create table if not exists fixes (
    id            uuid primary key default gen_random_uuid(),
    workflow_id   text,
    repo          text not null,
    sha           text not null,
    ref           text,
    status        text not null,                    -- converged | not_converged
    iterations    int,
    before_verdict text,
    verdict       jsonb not null default '{}'::jsonb,   -- judge output for the fixed run
    findings      jsonb not null default '[]'::jsonb,   -- judge/scan findings the fix targeted
    trajectory    jsonb not null default '[]'::jsonb,   -- the trace: ordered step objects
    patch         text,                             -- the unified diff Codex produced
    pr_url        text,
    created_at    timestamptz not null default now()
);
create index if not exists fixes_repo_idx on fixes(repo, created_at desc);
create index if not exists fixes_workflow_idx on fixes(workflow_id);

commit;
