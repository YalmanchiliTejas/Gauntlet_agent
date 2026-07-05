import { NextRequest, NextResponse } from "next/server";

import { backendFetch, getBackendSession } from "@/lib/server/gauntlet-backend";
import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";
import { rowToRun, RUN_COLUMNS_WITH_WORKFLOW, type RunRow } from "@/lib/server/workflow-map";
import { rowToSandbox, SANDBOX_COLUMNS, type SandboxRow } from "@/lib/server/sandbox-map";
import { mockRuns } from "@/lib/mock-data";

type ActiveScenarioRow = {
  id: string;
  seed: Record<string, unknown>;
};

type EnvKeyRow = {
  key: string;
};

type BackendInstallation = {
  installation_id: number;
};

type BackendBranch = {
  name: string;
  commit_sha?: string | null;
};

type WorkflowRow = {
  task_prompt: string | null;
  draft: { services?: Array<string | { name?: string }> } | null;
};

/** Resolve the HEAD SHA for a repo branch via the Gauntlet backend. */
async function resolveSha(
  repo: string,
  branch: string,
  installationId: number,
  request: NextRequest,
): Promise<string | null> {
  const [owner, name] = repo.split("/");
  if (!owner || !name) return null;
  try {
    const payload = await backendFetch<{ branches: BackendBranch[] }>(
      `/api/github/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/branches?installation_id=${installationId}`,
      undefined,
      request,
    );
    const match = payload.branches.find((b) => b.name === branch);
    return match?.commit_sha ?? null;
  } catch {
    return null;
  }
}

/** Resolve the user's GitHub App installation ID via the Gauntlet backend. */
async function resolveInstallationId(request: NextRequest): Promise<number | null> {
  try {
    const payload = await backendFetch<{ installations: BackendInstallation[] }>(
      "/api/github/installations",
      undefined,
      request,
    );
    return payload.installations[0]?.installation_id ?? null;
  } catch {
    return null;
  }
}

/** Dispatch a run Job to the Gauntlet backend sandbox runner. Returns true on success.
 *  workflow_id is set to the Supabase run ID so the poller can look it up later. */
async function dispatchRun(opts: {
  runId: string;
  repo: string;
  branch: string;
  sha: string;
  installationId: number;
  taskPrompt: string | null;
  twins: Record<string, string>;
  workflowId: string;
  request: NextRequest;
}): Promise<{ ok: boolean; error?: string }> {
  try {
    await backendFetch(
      "/api/sandbox/trigger",
      {
        method: "POST",
        body: JSON.stringify({
          repo: opts.repo,
          sha: opts.sha,
          ref: opts.branch,
          installation_id: opts.installationId,
          task_prompt: opts.taskPrompt,
          twins: Object.keys(opts.twins).length > 0 ? opts.twins : undefined,
          // Pass the Supabase run ID as workflow_id so the status poller can
          // find this job in the runner store without needing a callback URL.
          workflow_id: opts.runId,
          egress_default: "live",
        }),
      },
      opts.request,
    );
    return { ok: true };
  } catch (error) {
    const msg = error instanceof Error ? error.message : "Dispatch failed.";
    return { ok: false, error: msg };
  }
}

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await getServerSupabase();
  if (!supabase) {
    return NextResponse.json({ runs: mockRuns.filter((run) => run.sandboxId === id), source: "mock" });
  }
  const { data, error } = await supabase
    .from("sandbox_runs")
    .select(RUN_COLUMNS_WITH_WORKFLOW)
    .eq("sandbox_id", id)
    .order("created_at", { ascending: false });
  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 500 });
  }
  return NextResponse.json({ runs: (data as unknown as RunRow[]).map(rowToRun), source: "supabase" });
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json()) as { workflowId?: string };
  if (!body.workflowId) {
    return NextResponse.json({ detail: "workflowId is required." }, { status: 400 });
  }

  const supabase = await getServerSupabase();

  // ── Dev bypass: create a stubbed queued run without hitting the backend ──
  if (!supabase) {
    if (!isDevBypass()) {
      return NextResponse.json({ detail: "Sign in to start a run." }, { status: 401 });
    }
    return NextResponse.json(
      {
        run: {
          id: `run_local_${Date.now()}`,
          sandboxId: id,
          workflowId: body.workflowId,
          workflowName: null,
          fixOf: null,
          status: "queued",
          trajectory: [],
          verdict: {},
          review: { findings: [] },
          error: null,
          createdAt: new Date().toISOString(),
          finishedAt: null,
          scenarioId: null,
          initialState: {},
          finalState: {},
          stateDiff: {},
        },
        source: "dev-bypass",
      },
      { status: 201 },
    );
  }
  const db = supabase;

  // ── Fetch context needed for dispatch ─────────────────────────────────────
  const [sandboxResult, scenarioResult, envResult, workflowResult] = await Promise.all([
    supabase.from("sandboxes").select(SANDBOX_COLUMNS).eq("id", id).maybeSingle(),
    supabase.from("sandbox_scenarios").select("id, seed").eq("sandbox_id", id).eq("is_active", true).maybeSingle(),
    supabase.from("sandbox_env_vars").select("key").eq("sandbox_id", id).order("key", { ascending: true }),
    supabase
      .from("sandbox_workflows")
      .select("task_prompt, draft")
      .eq("id", body.workflowId)
      .maybeSingle(),
  ]);

  const sandbox = sandboxResult.data ? rowToSandbox(sandboxResult.data as SandboxRow) : null;
  const activeScenario = scenarioResult.data as ActiveScenarioRow | null;
  const envKeys = ((envResult.data as EnvKeyRow[] | null) ?? []).map((row) => row.key);
  const workflow = workflowResult.data as WorkflowRow | null;

  // ── Create the run row ────────────────────────────────────────────────────
  const { data, error } = await supabase
    .from("sandbox_runs")
    .insert({
      sandbox_id: id,
      workflow_id: body.workflowId,
      status: "queued",
      scenario_id: activeScenario?.id ?? null,
      initial_state: {
        scenario: activeScenario?.seed ?? {},
        envKeys,
      },
    })
    .select(RUN_COLUMNS_WITH_WORKFLOW)
    .single();

  if (error || !data) {
    return NextResponse.json({ detail: error?.message ?? "Could not start run." }, { status: 500 });
  }

  const run = rowToRun(data as unknown as RunRow);

  async function markDispatchError(message: string) {
    await db
      .from("sandbox_runs")
      .update({
        status: "error",
        error: message,
        finished_at: new Date().toISOString(),
      })
      .eq("id", run.id);
    run.status = "error";
    run.error = message;
  }

  // ── Dispatch to the sandbox runner (best-effort, non-blocking) ───────────
  if (!sandbox) {
    await markDispatchError("Sandbox not found.");
  } else {
    const session = await getBackendSession(request);
    if (!session.accessToken) {
      await markDispatchError("No backend bearer token is available. Sign in again or configure GAUNTLET_API_TOKEN.");
    } else {
      const installationId = await resolveInstallationId(request);
      if (installationId) {
        const sha = await resolveSha(sandbox.repo, sandbox.branch, installationId, request);
        if (sha) {
          const twins = sandbox.twinVersions ?? {};
          const taskPrompt = workflow?.task_prompt ?? null;
          const dispatch = await dispatchRun({
            runId: run.id,
            repo: sandbox.repo,
            branch: sandbox.branch,
            sha,
            installationId,
            taskPrompt,
            twins,
            workflowId: body.workflowId,
            request,
          });

          if (!dispatch.ok) {
            await markDispatchError(`Dispatch failed: ${dispatch.error}`);
          }
        } else {
          await markDispatchError(`Could not resolve SHA for ${sandbox.repo}@${sandbox.branch}`);
        }
      } else {
        await markDispatchError("No GitHub App installation found. Connect GitHub in sandbox settings.");
      }
    }
  }

  return NextResponse.json({ run, source: "supabase" }, { status: 201 });
}
