-- Reusable workflow library + sandbox assignment layer.
--
-- The existing `workflows` table was created by the old backend with a
-- project_id/config schema. This migration adapts it in-place by:
--   1. Making legacy NOT NULL columns nullable so new rows can omit them.
--   2. Adding the columns expected by the frontend (user_id, draft, etc.).
--   3. Adding workflow_id + assignment metadata to sandbox_workflows.
--   4. Backfilling sandbox_workflows rows into workflows as canonical records.
--
-- Safe to re-run: all changes use IF NOT EXISTS / IF EXISTS guards.

begin;

-- ── Step 1: Relax legacy NOT NULL constraints ─────────────────────────────
-- Old rows have project_id and config; new rows (from the UI) will not.
alter table workflows
    alter column project_id drop not null,
    alter column config set default '{}'::jsonb;

-- Make config nullable too so the backfill insert can omit it.
alter table workflows alter column config drop not null;

-- ── Step 2: Add columns expected by the frontend ──────────────────────────
alter table workflows
    add column if not exists user_id         uuid        references auth.users(id) on delete cascade,
    add column if not exists source_sandbox_id uuid       references sandboxes(id) on delete set null,
    add column if not exists description     text,
    add column if not exists difficulty      text,
    add column if not exists task_prompt     text,
    add column if not exists draft           jsonb       not null default '{}'::jsonb,
    add column if not exists focus           text,
    add column if not exists fingerprint     text;

-- ── Step 3: Indexes for new columns ──────────────────────────────────────
create index if not exists workflows_user_created_idx
    on workflows(user_id, created_at desc)
    where user_id is not null;

create index if not exists workflows_fingerprint_idx
    on workflows(user_id, fingerprint)
    where fingerprint is not null;

-- ── Step 4: Row-level security ────────────────────────────────────────────
-- Old rows have user_id = null (legacy); new rows are scoped to auth.uid().
alter table workflows enable row level security;

drop policy if exists workflows_own on workflows;
create policy workflows_own on workflows
    using  (user_id = auth.uid() or user_id is null)
    with check (user_id = auth.uid());

-- ── Step 5: Extend sandbox_workflows with assignment metadata ─────────────
alter table sandbox_workflows
    add column if not exists workflow_id          uuid        references workflows(id) on delete cascade,
    add column if not exists assigned_at          timestamptz not null default now(),
    add column if not exists enabled              boolean     not null default true,
    add column if not exists assignment_metadata  jsonb       not null default '{}'::jsonb;

-- ── Step 6: Backfill canonical workflow rows from sandbox_workflows ───────
-- Each existing sandbox_workflow becomes its own canonical workflow row.
-- We reuse the sandbox_workflow id so run references stay stable.
insert into workflows (
    id,
    user_id,
    source_sandbox_id,
    name,
    description,
    difficulty,
    task_prompt,
    draft,
    focus,
    fingerprint,
    created_at,
    updated_at
)
select
    sw.id,
    sw.user_id,
    sw.sandbox_id,
    sw.name,
    sw.description,
    sw.difficulty,
    sw.task_prompt,
    sw.draft,
    nullif(sw.draft->>'focus', ''),
    nullif(sw.draft->>'fingerprint', ''),
    sw.created_at,
    sw.created_at
from sandbox_workflows sw
where not exists (
    select 1 from workflows w where w.id = sw.id
);

-- ── Step 7: Link sandbox_workflows rows to their canonical workflow ────────
update sandbox_workflows
set workflow_id = id
where workflow_id is null;

-- ── Step 8: Indexes for the assignment join pattern ───────────────────────
create unique index if not exists sandbox_workflows_unique_assignment_idx
    on sandbox_workflows(sandbox_id, workflow_id)
    where workflow_id is not null;

create index if not exists sandbox_workflows_workflow_idx
    on sandbox_workflows(workflow_id, assigned_at desc);

commit;
