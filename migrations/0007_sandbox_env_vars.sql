-- Write-only environment variables for a sandbox. Values are stored so the
-- runner can inject them, but the web API only returns key names and timestamps.
-- Apply after 0003/0004/0005/0006.

begin;

create table if not exists sandbox_env_vars (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
    sandbox_id uuid not null references sandboxes(id) on delete cascade,
    key text not null,
    value text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (sandbox_id, key)
);

create index if not exists sandbox_env_vars_sandbox_idx
    on sandbox_env_vars(sandbox_id, key);

alter table sandbox_env_vars enable row level security;

create policy sandbox_env_vars_own on sandbox_env_vars
    using (user_id = auth.uid()) with check (user_id = auth.uid());

commit;
