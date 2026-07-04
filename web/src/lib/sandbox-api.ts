import {
  type Sandbox,
  type TwinOption,
} from "@/lib/mock-data";

export type Repository = {
  id: string;
  fullName: string;
  defaultBranch: string;
};

export type Branch = {
  name: string;
  protected: boolean;
};

export type GitHubConnection = {
  connected: boolean;
  installationId: number | null;
  source: "mock" | "github_app";
  reason?: "unauthenticated" | "no_installation" | "backend_unavailable";
  message: string;
  installUrl?: string;
};

export type CreateSandboxInput = {
  name?: string;
  repo: string;
  branch: string;
  // service id -> selected spec version
  twins: Record<string, string>;
};

export type SandboxOptionData = {
  connection: GitHubConnection;
  repositories: Repository[];
  twins: TwinOption[];
};

// ---------- workflows + runs ----------

export type DocInput = { title: string; text: string; url?: string };

export type Workflow = {
  id: string;
  sandboxId: string;
  name: string;
  description: string | null;
  difficulty: string | null;
  taskPrompt: string | null;
  services: string[];
  createdAt: string;
};

export type TraceStep = Record<string, unknown>;
export type RunStatus = "queued" | "running" | "passed" | "failed" | "error";

export type ReviewSeverity = "low" | "med" | "high";
// One judge finding, code-reviewer style: it tags specific trace steps.
export type ReviewFinding = {
  steps: number[]; // indices into trajectory this finding cites as evidence
  axis: string; // efficiency | correctness | reliability | security | …
  severity: ReviewSeverity;
  title: string;
  recommendation?: string;
};
export type RunReview = {
  summary?: string;
  reviewedAt?: string;
  findings: ReviewFinding[];
};

export type Run = {
  id: string;
  sandboxId: string;
  workflowId: string | null;
  workflowName: string | null;
  fixOf: string | null;
  status: RunStatus;
  trajectory: TraceStep[];
  verdict: Record<string, unknown>;
  review: RunReview;
  error: string | null;
  createdAt: string;
  finishedAt: string | null;
  scenarioId?: string | null;
  initialState?: Record<string, unknown>;
  finalState?: Record<string, unknown>;
  stateDiff?: Record<string, unknown>;
};

export type SimulationProfile = "baseline" | "busy" | "edge";
export type SimulationSeed = {
  service: string;
  version: string;
  resources: Record<string, unknown[]>;
};
export type SimulationScenario = {
  id?: string | null;
  sandboxId: string;
  name?: string;
  profile: SimulationProfile;
  generatedAt: string;
  seeds: SimulationSeed[];
};

export type SandboxEnvVar = {
  key: string;
  updatedAt: string;
};

export async function listWorkflows(): Promise<Workflow[]> {
  return (await fetchJson<{ workflows: Workflow[] }>("/api/workflows")).workflows;
}

export async function updateWorkflow(
  id: string,
  input: Pick<Workflow, "name" | "description" | "difficulty" | "taskPrompt" | "services">,
): Promise<Workflow> {
  return (
    await fetchJson<{ workflow: Workflow }>(`/api/workflows/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    })
  ).workflow;
}

export async function deleteWorkflow(id: string): Promise<void> {
  await fetchJson(`/api/workflows/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function generateWorkflows(input: {
  sandboxId: string;
  workflowName?: string;
  docs: DocInput[];
  services: { name: string; version?: string | null }[];
  count: number;
}): Promise<Workflow[]> {
  const payload = await fetchJson<{ workflows: Workflow[] }>(
    `/api/sandboxes/${encodeURIComponent(input.sandboxId)}/workflows`,
    { method: "POST", body: JSON.stringify(input) },
  );
  return payload.workflows;
}

export async function listRuns(): Promise<Run[]> {
  return (await fetchJson<{ runs: Run[] }>("/api/runs")).runs;
}

export async function getRun(id: string): Promise<Run> {
  return (await fetchJson<{ run: Run }>(`/api/runs/${encodeURIComponent(id)}`)).run;
}

export async function createRun(sandboxId: string, workflowId: string): Promise<Run> {
  const payload = await fetchJson<{ run: Run }>(
    `/api/sandboxes/${encodeURIComponent(sandboxId)}/runs`,
    { method: "POST", body: JSON.stringify({ workflowId }) },
  );
  return payload.run;
}

export async function fixRun(id: string): Promise<Run> {
  return (await fetchJson<{ run: Run }>(`/api/runs/${encodeURIComponent(id)}/fix`, { method: "POST" }))
    .run;
}

export async function reviewRun(id: string): Promise<Run> {
  return (
    await fetchJson<{ run: Run }>(`/api/runs/${encodeURIComponent(id)}/review`, { method: "POST" })
  ).run;
}

export async function listSandboxOptions(): Promise<SandboxOptionData> {
  return fetchJson<SandboxOptionData>("/api/sandboxes/options");
}

export async function listSandboxes(): Promise<Sandbox[]> {
  const payload = await fetchJson<{ sandboxes: Sandbox[] }>("/api/sandboxes");
  return payload.sandboxes;
}

export async function getSandbox(id: string): Promise<Sandbox> {
  const payload = await fetchJson<{ sandbox: Sandbox }>(`/api/sandboxes/${encodeURIComponent(id)}`);
  return payload.sandbox;
}

export async function updateSandboxTwins(id: string, twins: Record<string, string>): Promise<Sandbox> {
  const payload = await fetchJson<{ sandbox: Sandbox }>(`/api/sandboxes/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ twins }),
  });
  return payload.sandbox;
}

export async function generateSimulationScenario(
  sandboxId: string,
  profile: SimulationProfile,
): Promise<SimulationScenario> {
  return (
    await fetchJson<{ scenario: SimulationScenario }>(
      `/api/sandboxes/${encodeURIComponent(sandboxId)}/simulation`,
      { method: "POST", body: JSON.stringify({ profile }) },
    )
  ).scenario;
}

export async function getSimulationScenario(sandboxId: string): Promise<SimulationScenario | null> {
  return (
    await fetchJson<{ scenario: SimulationScenario | null }>(
      `/api/sandboxes/${encodeURIComponent(sandboxId)}/simulation`,
    )
  ).scenario;
}

export async function saveSimulationScenario(
  sandboxId: string,
  scenario: SimulationScenario,
): Promise<SimulationScenario> {
  return (
    await fetchJson<{ scenario: SimulationScenario }>(
      `/api/sandboxes/${encodeURIComponent(sandboxId)}/simulation`,
      { method: "PUT", body: JSON.stringify({ scenario }) },
    )
  ).scenario;
}

export async function listSandboxEnvVars(sandboxId: string): Promise<SandboxEnvVar[]> {
  return (
    await fetchJson<{ env: SandboxEnvVar[] }>(`/api/sandboxes/${encodeURIComponent(sandboxId)}/env`)
  ).env;
}

export async function saveSandboxEnvVars(
  sandboxId: string,
  env: { key: string; value: string }[],
): Promise<SandboxEnvVar[]> {
  return (
    await fetchJson<{ env: SandboxEnvVar[] }>(`/api/sandboxes/${encodeURIComponent(sandboxId)}/env`, {
      method: "PUT",
      body: JSON.stringify({ env }),
    })
  ).env;
}

export async function deleteSandboxEnvVar(sandboxId: string, key: string): Promise<void> {
  await fetchJson(
    `/api/sandboxes/${encodeURIComponent(sandboxId)}/env?key=${encodeURIComponent(key)}`,
    { method: "DELETE" },
  );
}

export async function listBranches(
  repo: string,
  installationId?: number | null,
): Promise<Branch[]> {
  const params = new URLSearchParams({ repo });
  if (installationId) {
    params.set("installationId", String(installationId));
  }
  const payload = await fetchJson<{ branches: Branch[] }>(`/api/sandboxes/branches?${params}`);
  return payload.branches;
}

export async function createSandbox(input: CreateSandboxInput): Promise<Sandbox> {
  // Explicit payload so exactly these fields are JSON-encoded and sent.
  const payload = {
    name: input.name?.trim() || undefined,
    repo: input.repo,
    branch: input.branch,
    twins: input.twins, // { [serviceId]: version }
  };
  const response = await fetchJson<{ sandbox: Sandbox }>("/api/sandboxes", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return response.sandbox;
}

export async function linkGitHubInstallation(installationId: string): Promise<void> {
  await fetchJson("/api/github/installations", {
    method: "POST",
    body: JSON.stringify({ installationId }),
  });
}

export async function signInWithToken(accessToken: string): Promise<void> {
  await fetchJson("/api/session", {
    method: "POST",
    body: JSON.stringify({ accessToken }),
  });
}

export async function signOut(): Promise<void> {
  await fetchJson("/api/session", { method: "DELETE" });
}

export const requiredGithubUiEndpoints = [
  "GET /api/github/installations",
  "GET /api/github/repositories",
  "GET /api/github/repositories/{owner}/{repo}/branches",
  "GET /api/sandboxes/options",
  "GET /api/sandboxes/branches",
  "POST /api/github/installations",
  "POST /api/sandboxes",
  "GET /api/sandboxes",
];

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail || `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }
  return payload as T;
}
