-- Fix: inserts into `workflows` failed the RLS `with check (user_id = auth.uid())`
-- because 0007 added user_id with no default, so it came in NULL. Give it the same
-- default auth.uid() that sandbox_workflows (0004) already has, so new rows auto-scope
-- to the signed-in user. Apply after 0007.

begin;

alter table workflows alter column user_id set default auth.uid();

commit;
