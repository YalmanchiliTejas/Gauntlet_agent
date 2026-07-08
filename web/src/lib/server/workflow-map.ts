import type { Run, RunReview, RunStatus, Workflow } from "@/lib/sandbox-api";

// ---------- reusable workflows + sandbox assignments ----------

export const WORKFLOW_COLUMNS =
  "id, sandbox_id, workflow_id, name, description, difficulty, task_prompt, draft, created_at, workflows ( id, source_sandbox_id, name, description, difficulty, task_prompt, draft, focus, fingerprint, created_at )";

export const LEGACY_WORKFLOW_COLUMNS =
  "id, sandbox_id, name, description, difficulty, task_prompt, draft, created_at";

export const CANONICAL_WORKFLOW_COLUMNS =
  "id, source_sandbox_id, name, description, difficulty, task_prompt, draft, focus, fingerprint, created_at, sandbox_workflows ( id, sandbox_id )";

export type WorkflowAssignmentRef = {
  id: string;
  sandbox_id: string;
};

export type CanonicalWorkflowRow = {
  id: string;
  source_sandbox_id: string | null;
  name: string;
  description: string | null;
  difficulty: string | null;
  task_prompt: string | null;
  draft: WorkflowDraftData | null;
  focus: string | null;
  fingerprint: string | null;
  created_at: string;
  sandbox_workflows?: WorkflowAssignmentRef[] | null;
};

export type WorkflowDraftData = {
  services?: Array<string | { name?: string }>;
  focus?: string | null;
  fingerprint?: string | null;
  novelty_reason?: string | null;
  selection_reason?: string | null;
};

export type WorkflowRow = {
  id: string;
  sandbox_id: string;
  workflow_id?: string | null;
  name: string;
  description: string | null;
  difficulty: string | null;
  task_prompt: string | null;
  draft: WorkflowDraftData | null;
  created_at: string;
  workflows?: CanonicalWorkflowRow | CanonicalWorkflowRow[] | null;
};

export function rowToWorkflow(row: WorkflowRow): Workflow {
  const canonical = Array.isArray(row.workflows) ? row.workflows[0] : row.workflows;
  const draft = canonical?.draft ?? row.draft;
  const services = (draft?.services ?? [])
    .map((service) => (typeof service === "string" ? service : service?.name))
    .filter((name): name is string => Boolean(name));
  return {
    id: row.id,
    sandboxId: row.sandbox_id,
    canonicalId: row.workflow_id ?? canonical?.id ?? row.id,
    assignmentId: row.id,
    sourceSandboxId: canonical?.source_sandbox_id ?? row.sandbox_id,
    name: canonical?.name ?? row.name,
    description: canonical?.description ?? row.description,
    difficulty: canonical?.difficulty ?? row.difficulty,
    taskPrompt: canonical?.task_prompt ?? row.task_prompt,
    services,
    focus: canonical?.focus ?? draft?.focus ?? null,
    fingerprint: canonical?.fingerprint ?? draft?.fingerprint ?? null,
    noveltyReason: draft?.novelty_reason ?? draft?.selection_reason ?? null,
    createdAt: canonical?.created_at ?? row.created_at,
  };
}

export function canonicalRowToWorkflow(row: CanonicalWorkflowRow): Workflow {
  const assignments = row.sandbox_workflows ?? [];
  const firstAssignment = assignments[0] ?? null;
  const services = (row.draft?.services ?? [])
    .map((service) => (typeof service === "string" ? service : service?.name))
    .filter((name): name is string => Boolean(name));
  return {
    id: row.id,
    canonicalId: row.id,
    assignmentId: firstAssignment?.id ?? null,
    sandboxId: firstAssignment?.sandbox_id ?? row.source_sandbox_id ?? "",
    sandboxIds: assignments.map((assignment) => assignment.sandbox_id),
    assignedSandboxCount: assignments.length,
    sourceSandboxId: row.source_sandbox_id,
    name: row.name,
    description: row.description,
    difficulty: row.difficulty,
    taskPrompt: row.task_prompt,
    services,
    focus: row.focus ?? row.draft?.focus ?? null,
    fingerprint: row.fingerprint ?? row.draft?.fingerprint ?? null,
    noveltyReason: row.draft?.novelty_reason ?? row.draft?.selection_reason ?? null,
    createdAt: row.created_at,
  };
}

// ---------- sandbox_runs ----------

export const RUN_COLUMNS =
  "id, sandbox_id, workflow_id, fix_of, status, trajectory, verdict, review, error, created_at, finished_at, scenario_id, initial_state, final_state, state_diff";
// Same columns plus the workflow name (embedded resource) for list/detail views.
export const RUN_COLUMNS_WITH_WORKFLOW = `${RUN_COLUMNS}, sandbox_workflows ( name, workflows ( name ) )`;

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
  sandbox_workflows?: { name: string; workflows?: { name: string } | null } | null;
};

export function rowToRun(row: RunRow): Run {
  return {
    id: row.id,
    sandboxId: row.sandbox_id,
    workflowId: row.workflow_id,
    workflowName: row.sandbox_workflows?.workflows?.name ?? row.sandbox_workflows?.name ?? null,
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
