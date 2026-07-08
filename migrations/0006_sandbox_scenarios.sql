-- Durable scenario seed data for sandbox twins. A scenario is the per-sandbox
-- overlay applied on top of twins/registry/<service>/<version>/seed.json before
-- a run starts. Runs snapshot the active scenario so the initial state is
-- reproducible even if the sandbox scenario is edited later.
-- Apply by pasting into the Supabase SQL editor, or:
--   psql "$DATABASE_URL" -f migrations/0006_sandbox_scenarios.sql

begin;

create table if not exists sandbox_scenarios (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    sandbox_id uuid not null references sandboxes(id) on delete cascade,
    name text not null default 'Default scenario',
    profile text not null default 'baseline',
    seed jsonb not null default '{}'::jsonb,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists sandbox_scenarios_sandbox_idx
    on sandbox_scenarios(sandbox_id, updated_at desc);
create unique index if not exists sandbox_scenarios_one_active_idx
    on sandbox_scenarios(sandbox_id)
    where is_active;

alter table sandbox_scenarios enable row level security;

create policy sandbox_scenarios_own on sandbox_scenarios
    using (user_id = auth.uid()) with check (user_id = auth.uid());

alter table sandbox_runs add column if not exists scenario_id uuid references sandbox_scenarios(id) on delete set null;
alter table sandbox_runs add column if not exists initial_state jsonb not null default '{}'::jsonb;
alter table sandbox_runs add column if not exists final_state jsonb not null default '{}'::jsonb;
alter table sandbox_runs add column if not exists state_diff jsonb not null default '{}'::jsonb;

commit;
