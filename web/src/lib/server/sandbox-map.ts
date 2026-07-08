import { twinOptions, type Sandbox } from "@/lib/mock-data";

// A row from the `sandboxes` table (see migrations/0003_sandboxes.sql).
export type SandboxRow = {
  id: string;
  name: string;
  repo: string;
  branch: string;
  status: Sandbox["status"];
  twins: Record<string, string> | null;
  workflow_count: number | null;
  last_run_at: string | null;
};

export const SANDBOX_COLUMNS =
  "id, name, repo, branch, status, twins, workflow_count, last_run_at";

export function rowToSandbox(row: SandboxRow): Sandbox {
  const twinsMap = row.twins ?? {};
  return {
    id: row.id,
    name: row.name,
    repo: row.repo,
    branch: row.branch,
    status: row.status,
    twins: Object.keys(twinsMap).map(
      (id) => twinOptions.find((twin) => twin.id === id)?.name ?? id,
    ),
    twinVersions: twinsMap,
    workflowCount: row.workflow_count ?? 0,
    lastRun: row.last_run_at ? new Date(row.last_run_at).toLocaleDateString() : "Never run",
  };
}
