-- Backend for commercial use: user accounts, runs (agent trace + judge verdict),
-- and generated workflows. Apply by pasting into the Supabase SQL editor, or:
--   psql "$DATABASE_URL" -f migrations/0001_backend.sql
-- Mirrors the storage pattern in ~/Desktop/temp/Gauntlet (psycopg + Supabase Postgres).

begin;

create extension if not exists "pgcrypto";  -- gen_random_uuid()

-- Commercial accounts. A user is identified by email and/or the GitHub App
-- installation that triggers their runs; Slack/UI triggers reuse the same row.
create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    email text unique,
    github_installation_id bigint unique,
    plan text not null default 'free',
    created_at timestamptz not null default now()
);

-- One gauntlet evaluation of a commit: the captured agent trajectory (trace)
-- plus the judge verdict. status: running | passed | failed | error | canceled.
create table if not exists runs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references users(id) on delete set null,
    repo text not null,
    sha text not null,
    ref text,
    status text not null default 'running',
    exit_code int,
    verdict jsonb not null default '{}'::jsonb,      -- judge output: verdict, issues, note
    trajectory jsonb not null default '[]'::jsonb,   -- the trace: ordered step objects
    error text,
    created_at timestamptz not null default now(),
    finished_at timestamptz
);
create index if not exists runs_user_idx on runs(user_id, created_at desc);
create index if not exists runs_repo_idx on runs(repo, created_at desc);

-- Generated workflow drafts, kept per user.
create table if not exists workflows (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references users(id) on delete set null,
    name text not null,
    difficulty text,
    draft jsonb not null,                            -- full WorkflowDraft
    created_at timestamptz not null default now()
);
create index if not exists workflows_user_idx on workflows(user_id, created_at desc);

commit;
