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
  repo: string;
  branch: string;
  twinIds: string[];
};

export type SandboxOptionData = {
  connection: GitHubConnection;
  repositories: Repository[];
  twins: TwinOption[];
};

export async function listSandboxOptions(): Promise<SandboxOptionData> {
  return fetchJson<SandboxOptionData>("/api/sandboxes/options");
}

export async function listSandboxes(): Promise<Sandbox[]> {
  const payload = await fetchJson<{ sandboxes: Sandbox[] }>("/api/sandboxes");
  return payload.sandboxes;
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
  const payload = await fetchJson<{ sandbox: Sandbox }>("/api/sandboxes", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return payload.sandbox;
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
