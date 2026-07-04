import type { Run, RunReview, RunStatus, Workflow } from "@/lib/sandbox-api";

// ---------- sandbox_workflows ----------

export const WORKFLOW_COLUMNS =
  "id, sandbox_id, name, description, difficulty, task_prompt, draft, created_at";

export type WorkflowRow = {
  id: string;
  sandbox_id: string;
  name: string;
  description: string | null;
  difficulty: string | null;
  task_prompt: string | null;
  draft: { services?: Array<string | { name?: string }> } | null;
  created_at: string;
};

export function rowToWorkflow(row: WorkflowRow): Workflow {
  const services = (row.draft?.services ?? [])
    .map((service) => (typeof service === "string" ? service : service?.name))
    .filter((name): name is string => Boolean(name));
  return {
    id: row.id,
    sandboxId: row.sandbox_id,
    name: row.name,
    description: row.description,
    difficulty: row.difficulty,
    taskPrompt: row.task_prompt,
    services,
    createdAt: row.created_at,
  };
}

// ---------- sandbox_runs ----------

export const RUN_COLUMNS =
  "id, sandbox_id, workflow_id, fix_of, status, trajectory, verdict, review, error, created_at, finished_at, scenario_id, initial_state, final_state, state_diff";
// Same columns plus the workflow name (embedded resource) for list/detail views.
export const RUN_COLUMNS_WITH_WORKFLOW = `${RUN_COLUMNS}, sandbox_workflows ( name )`;

export type RunRow = {
  id: string;
  sandbox_id: string;
  workflow_id: string | null;
  fix_of: string | null;
  status: string;
  trajectory: unknown;
  verdict: Record<string, unknown> | null;
  review: RunReview | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  scenario_id?: string | null;
  initial_state?: Record<string, unknown> | null;
  final_state?: Record<string, unknown> | null;
  state_diff?: Record<string, unknown> | null;
  sandbox_workflows?: { name: string } | null;
};

export function rowToRun(row: RunRow): Run {
  return {
    id: row.id,
    sandboxId: row.sandbox_id,
    workflowId: row.workflow_id,
    workflowName: row.sandbox_workflows?.name ?? null,
    fixOf: row.fix_of,
    status: (row.status as RunStatus) ?? "queued",
    trajectory: Array.isArray(row.trajectory) ? (row.trajectory as Run["trajectory"]) : [],
    verdict: row.verdict ?? {},
    review: row.review?.findings ? row.review : { findings: [] },
    error: row.error,
    createdAt: row.created_at,
    finishedAt: row.finished_at,
    scenarioId: row.scenario_id ?? null,
    initialState: row.initial_state ?? {},
    finalState: row.final_state ?? {},
    stateDiff: row.state_diff ?? {},
  };
}
