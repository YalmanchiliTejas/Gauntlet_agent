"""Supabase/Postgres persistence for users, runs (trace + verdict), and workflows.

Same pattern as ~/Desktop/temp/Gauntlet: a psycopg connection pool with
`dict_row`, one connection borrowed per method. Configured via DATABASE_URL
(or SUPABASE_DB_URL). When unset, the store is a no-op so local/dev runs and
tests keep working without a database — persistence is best-effort and must
never break a run.

    python -m gauntlet.store   # self-check (no DB required)
"""
from __future__ import annotations

import json
import os
from typing import Any

_DB_URL = os.environ.get("DATABASE_URL") or os.environ.get("SUPABASE_DB_URL", "")

_pool: Any = None
_store: "Store | None" = None


def _jsonb(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def _get_pool() -> Any:
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        from psycopg.rows import dict_row

        # prepare_threshold=None: no implicit prepared statements, required for Supabase's
        # pgbouncer transaction-mode pooler (else "prepared statement _pg3_* does not exist").
        _pool = ConnectionPool(_DB_URL, kwargs={"row_factory": dict_row, "prepare_threshold": None},
                               min_size=1, max_size=10, open=True)
    return _pool


class Store:
    """All backend reads/writes. Methods are no-ops (return None/[]) when no
    DATABASE_URL is configured, so callers never need to guard for it."""

    @property
    def enabled(self) -> bool:
        return bool(_DB_URL)

    def _exec(self, sql: str, params: tuple, *, fetch: str | None = None) -> Any:
        if not self.enabled:
            return None if fetch == "one" else [] if fetch == "all" else None
        with _get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return list(cur.fetchall())
                return None

    # ---------- users ----------

    def upsert_user(self, *, email: str | None = None,
                    github_installation_id: int | None = None,
                    plan: str = "free") -> dict | None:
        """Find-or-create by installation id (preferred) or email. Returns the row."""
        if github_installation_id is not None:
            return self._exec(
                """
                insert into users (github_installation_id, email, plan)
                values (%s, %s, %s)
                on conflict (github_installation_id) do update
                    set email = coalesce(excluded.email, users.email)
                returning id, email, github_installation_id, plan, created_at
                """,
                (github_installation_id, email, plan), fetch="one")
        if email is not None:
            return self._exec(
                """
                insert into users (email, plan) values (%s, %s)
                on conflict (email) do update set plan = users.plan
                returning id, email, github_installation_id, plan, created_at
                """,
                (email, plan), fetch="one")
        return None

    def get_user(self, user_id: str) -> dict | None:
        return self._exec(
            "select id, email, github_installation_id, plan, created_at from users where id = %s",
            (user_id,), fetch="one")

    # ---------- runs (agent trace + judge verdict) ----------

    def create_run(self, *, user_id: str | None, repo: str, sha: str,
                   ref: str | None, workflow_id: str | None = None) -> str | None:
        row = self._exec(
            "insert into runs (user_id, repo, sha, ref, workflow_id) "
            "values (%s, %s, %s, %s, %s) returning id",
            (user_id, repo, sha, ref, workflow_id), fetch="one")
        return str(row["id"]) if row else None

    def finish_run(self, *, run_id: str | None, status: str,
                   exit_code: int | None = None, verdict: dict | None = None,
                   trajectory: list[dict] | None = None, error: str | None = None) -> None:
        if not run_id:
            return
        self._exec(
            """
            update runs set status = %s, exit_code = %s,
                verdict = coalesce(%s, verdict), trajectory = coalesce(%s, trajectory),
                error = %s, finished_at = now()
            where id = %s
            """,
            (status, exit_code,
             _jsonb(verdict) if verdict is not None else None,
             _jsonb(trajectory) if trajectory is not None else None,
             error, run_id))

    def get_run(self, run_id: str) -> dict | None:
        return self._exec(
            "select id, user_id, workflow_id, repo, sha, ref, status, exit_code, verdict, "
            "trajectory, error, created_at, finished_at from runs where id = %s",
            (run_id,), fetch="one")

    def get_run_by_workflow_id(self, workflow_id: str) -> dict | None:
        """Look up a run by the caller-supplied workflow_id (e.g. the Supabase run UUID)."""
        return self._exec(
            "select id, user_id, workflow_id, repo, sha, ref, status, exit_code, verdict, "
            "trajectory, error, created_at, finished_at from runs where workflow_id = %s "
            "order by created_at desc limit 1",
            (workflow_id,), fetch="one")

    def list_runs(self, *, user_id: str | None = None, repo: str | None = None,
                  limit: int = 50) -> list[dict]:
        limit = max(1, min(limit, 200))
        clauses, params = [], []
        if user_id:
            clauses.append("user_id = %s"); params.append(user_id)
        if repo:
            clauses.append("repo = %s"); params.append(repo)
        where = ("where " + " and ".join(clauses)) if clauses else ""
        return self._exec(
            f"select id, user_id, workflow_id, repo, sha, ref, status, exit_code, verdict, error, "
            f"created_at, finished_at from runs {where} order by created_at desc limit %s",
            (*params, limit), fetch="all")

    # ---------- workflows ----------

    def save_workflows(self, *, user_id: str | None, drafts: list[dict]) -> list[str]:
        ids: list[str] = []
        for d in drafts:
            row = self._exec(
                "insert into workflows (user_id, name, difficulty, draft) "
                "values (%s, %s, %s, %s) returning id",
                (user_id, str(d.get("name") or "workflow"), d.get("difficulty"), _jsonb(d)),
                fetch="one")
            if row:
                ids.append(str(row["id"]))
        return ids

    def get_workflow(self, workflow_id: str) -> dict | None:
        return self._exec(
            "select id, user_id, name, difficulty, draft, created_at from workflows where id = %s",
            (workflow_id,), fetch="one")

    def list_workflows(self, *, user_id: str | None = None, limit: int = 50) -> list[dict]:
        limit = max(1, min(limit, 200))
        if user_id:
            return self._exec(
                "select id, user_id, name, difficulty, created_at from workflows "
                "where user_id = %s order by created_at desc limit %s",
                (user_id, limit), fetch="all")
        return self._exec(
            "select id, user_id, name, difficulty, created_at from workflows "
            "order by created_at desc limit %s",
            (limit,), fetch="all")


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def read_trajectory(path) -> list[dict]:
    """Load a trajectory JSONL file into a list of step dicts (for persistence)."""
    try:
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError):
        return []


if __name__ == "__main__":
    # No-DB self-check: unconfigured store must degrade to no-ops, never raise.
    assert not os.environ.get("DATABASE_URL"), "run without DATABASE_URL"
    s = store()
    assert s.enabled is False
    assert s.upsert_user(email="a@b.com") is None
    assert s.create_run(user_id=None, repo="x/y", sha="abc", ref="main") is None
    s.finish_run(run_id=None, status="passed")  # no-op, no crash
    assert s.list_runs() == []
    assert s.save_workflows(user_id=None, drafts=[{"name": "w"}]) == []
    assert s.list_workflows() == []
    assert read_trajectory("/nonexistent") == []
    print("ok")
