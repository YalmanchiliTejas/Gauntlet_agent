-- Link a run to the workflow it executed (a /workflows/{id}/run job).
alter table runs add column if not exists workflow_id uuid references workflows(id) on delete set null;
create index if not exists runs_workflow_idx on runs(workflow_id, created_at desc);
