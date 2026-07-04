-- Sandboxes created from the web UI: a repo + branch + the service twins (and
-- their pinned spec versions) an agent runs against. Owned per Supabase auth
-- user and read/written directly from the web app under RLS.
-- Apply by pasting into the Supabase SQL editor, or:
--   psql "$DATABASE_URL" -f migrations/0003_sandboxes.sql

begin;

create table if not exists sandboxes (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    name text not null,
    repo text not null,
    branch text not null,
    status text not null default 'Ready',
    twins jsonb not null default '{}'::jsonb,        -- {service: version} map
    workflow_count int not null default 0,
    last_run_at timestamptz,                         -- null = never run
    created_at timestamptz not null default now()
);
create index if not exists sandboxes_user_idx on sandboxes(user_id, created_at desc);

-- Per-user isolation: a signed-in user only ever sees/edits their own rows.
alter table sandboxes enable row level security;

create policy sandboxes_select_own on sandboxes
    for select using (user_id = auth.uid());
create policy sandboxes_insert_own on sandboxes
    for insert with check (user_id = auth.uid());
create policy sandboxes_update_own on sandboxes
    for update using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy sandboxes_delete_own on sandboxes
    for delete using (user_id = auth.uid());

commit;
