-- Web-UI workflows and their execution runs (traces), scoped to a sandbox and
-- owned per Supabase auth user under RLS. Named `sandbox_*` to avoid colliding
-- with the backend's own users-keyed `workflows`/`runs` tables (0001) in the
-- same database.
-- Apply by pasting into the Supabase SQL editor, or:
--   psql "$DATABASE_URL" -f migrations/0004_sandbox_workflows_runs.sql

begin;

-- A generated workflow draft (from docs + services + human input).
create table if not exists sandbox_workflows (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    sandbox_id uuid not null references sandboxes(id) on delete cascade,
    name text not null,
    description text,
    difficulty text,
    task_prompt text,
    draft jsonb not null default '{}'::jsonb,        -- full generated WorkflowDraft
    created_at timestamptz not null default now()
);
create index if not exists sandbox_workflows_sandbox_idx
    on sandbox_workflows(sandbox_id, created_at desc);

-- One execution of a workflow: the captured trajectory (trace) + judge verdict.
-- status: queued | running | passed | failed | error.
create table if not exists sandbox_runs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    sandbox_id uuid not null references sandboxes(id) on delete cascade,
    workflow_id uuid references sandbox_workflows(id) on delete set null,
    fix_of uuid references sandbox_runs(id) on delete set null,  -- set when this is a fix attempt
    status text not null default 'queued',
    trajectory jsonb not null default '[]'::jsonb,   -- ordered trace steps
    verdict jsonb not null default '{}'::jsonb,      -- judge output
    error text,
    created_at timestamptz not null default now(),
    finished_at timestamptz
);
create index if not exists sandbox_runs_sandbox_idx on sandbox_runs(sandbox_id, created_at desc);
create index if not exists sandbox_runs_workflow_idx on sandbox_runs(workflow_id, created_at desc);

-- Per-user isolation.
alter table sandbox_workflows enable row level security;
alter table sandbox_runs enable row level security;

create policy sandbox_workflows_own on sandbox_workflows
    using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy sandbox_runs_own on sandbox_runs
    using (user_id = auth.uid()) with check (user_id = auth.uid());

commit;
