import { NextRequest, NextResponse } from "next/server";

import { backendFetch } from "@/lib/server/gauntlet-backend";
import { rowToSandbox, SANDBOX_COLUMNS, type SandboxRow } from "@/lib/server/sandbox-map";
import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";
import { rowToRun, RUN_COLUMNS_WITH_WORKFLOW, type RunRow } from "@/lib/server/workflow-map";

async function resolveInstallationId(request: NextRequest): Promise<number | null> {
  try {
    const p = await backendFetch<{ installations: { installation_id: number }[] }>(
      "/api/github/installations",
      undefined,
      request,
    );
    return p.installations[0]?.installation_id ?? null;
  } catch {
    return null;
  }
}

async function resolveSha(
  repo: string,
  branch: string,
  installationId: number,
  request: NextRequest,
): Promise<string | null> {
  const [owner, name] = repo.split("/");
  if (!owner || !name) return null;
  try {
    const p = await backendFetch<{ branches: { name: string; commit_sha?: string | null }[] }>(
      `/api/github/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/branches?installation_id=${installationId}`,
      undefined,
      request,
    );
    return p.branches.find((b) => b.name === branch)?.commit_sha ?? null;
  } catch {
    return null;
  }
}

// The "fix" button: spawn a fix attempt off an existing run, then dispatch the backend
// find-and-fix loop (which reports its outcome back via the store-runs callback, so the
// fix run resolves in the UI instead of hanging at "queued").
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await getServerSupabase();
  if (!supabase) {
    if (!isDevBypass()) {
      return NextResponse.json({ detail: "Sign in to start a fix." }, { status: 401 });
    }
    return NextResponse.json(
      {
        run: {
          id: `run_fix_${Date.now()}`,
          sandboxId: "",
          workflowId: null,
          workflowName: null,
          fixOf: id,
          status: "queued",
          trajectory: [],
          verdict: {},
          review: { findings: [] },
          error: null,
          createdAt: new Date().toISOString(),
          finishedAt: null,
        },
        source: "dev-bypass",
      },
      { status: 201 },
    );
  }

  const { data: source, error: findError } = await supabase
    .from("sandbox_runs")
    .select("sandbox_id, workflow_id, verdict, trajectory")
    .eq("id", id)
    .maybeSingle();
  if (findError) return NextResponse.json({ detail: findError.message }, { status: 500 });
  if (!source) return NextResponse.json({ detail: "Run not found." }, { status: 404 });

  const sandboxId = (source as { sandbox_id: string }).sandbox_id;
  const workflowId = (source as { workflow_id: string | null }).workflow_id;
  // Carry the run's own judge findings into the fix so the fixer targets exactly those
  // instead of re-discovering with a fresh (stochastic) judge pass.
  const seedVerdict = (source as { verdict: Record<string, unknown> | null }).verdict;
  const seedTrajectory = (source as { trajectory: unknown }).trajectory;

  const { data: sbRow } = await supabase
    .from("sandboxes")
    .select(SANDBOX_COLUMNS)
    .eq("id", sandboxId)
    .maybeSingle();
  const sandbox = sbRow ? rowToSandbox(sbRow as SandboxRow) : null;

  // Create the fix run row (linked back via fix_of).
  const { data, error } = await supabase
    .from("sandbox_runs")
    .insert({ sandbox_id: sandboxId, workflow_id: workflowId, fix_of: id, status: "queued" })
    .select(RUN_COLUMNS_WITH_WORKFLOW)
    .single();
  if (error || !data) {
    return NextResponse.json({ detail: error?.message ?? "Could not start fix." }, { status: 500 });
  }
  const run = rowToRun(data as unknown as RunRow);

  // Dispatch the backend fix loop. Mark the run errored (not hung) if we can't.
  const fail = async (message: string) => {
    await supabase
      .from("sandbox_runs")
      .update({ status: "error", error: message, finished_at: new Date().toISOString() })
      .eq("id", run.id);
    run.status = "error";
    run.error = message;
  };

  if (!sandbox) {
    await fail("Fix dispatch failed: sandbox not found for this run.");
  } else {
    const installationId = await resolveInstallationId(request);
    const sha = installationId ? await resolveSha(sandbox.repo, sandbox.branch, installationId, request) : null;
    if (!installationId || !sha) {
      await fail(`Fix dispatch failed: could not resolve ${sandbox.repo}@${sandbox.branch}.`);
    } else {
      try {
        await backendFetch(
          "/api/sandbox/fix",
          {
            method: "POST",
            body: JSON.stringify({
              repo: sandbox.repo,
              sha,
              ref: sandbox.branch,
              installation_id: installationId,
              workflow_id: run.id, // the fixer reports back keyed by this
              seed_verdict: seedVerdict,
              seed_trajectory: Array.isArray(seedTrajectory) ? seedTrajectory : undefined,
            }),
          },
          request,
        );
        const { data: accepted } = await supabase
          .from("sandbox_runs")
          .update({ status: "running" })
          .eq("id", run.id)
          .select(RUN_COLUMNS_WITH_WORKFLOW)
          .single();
        if (accepted) {
          return NextResponse.json({ run: rowToRun(accepted as unknown as RunRow), source: "supabase" }, { status: 201 });
        }
        run.status = "running";
      } catch (e) {
        await fail(`Fix dispatch failed: ${e instanceof Error ? e.message : String(e)}`);
      }
    }
  }

  return NextResponse.json({ run, source: "supabase" }, { status: 201 });
}
