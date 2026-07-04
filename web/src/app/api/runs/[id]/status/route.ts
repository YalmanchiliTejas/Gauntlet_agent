import { NextRequest, NextResponse } from "next/server";

import { backendFetch, getBackendSession } from "@/lib/server/gauntlet-backend";
import { getServerSupabase } from "@/lib/server/supabase";
import { rowToRun, RUN_COLUMNS_WITH_WORKFLOW, type RunRow } from "@/lib/server/workflow-map";

// Runner statuses that are terminal (no further updates expected).
const TERMINAL = new Set(["succeeded", "failed", "canceled", "error"]);

// Map runner store status values to sandbox_runs status values.
const STATUS_MAP: Record<string, string> = {
  passed: "succeeded",
  failed: "failed",
  error: "failed",
  canceled: "canceled",
};

type RunnerStatus = {
  found: boolean;
  status?: string;
  verdict?: Record<string, unknown> | null;
  error?: string | null;
  exit_code?: number | null;
  finished_at?: string | null;
};

/**
 * GET /api/runs/[id]/status
 *
 * Polling endpoint for active runs. Reads the run from Supabase first. If it
 * is still queued/running, asks the backend runner store for an update
 * (GET /api/sandbox/run-status?workflow_id={id}). When the runner reports the
 * run is done, writes the result back to Supabase and returns the final row.
 *
 * No callback URL or shared secret needed — the frontend polls this until the
 * status is terminal.
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const supabase = await getServerSupabase();
  if (!supabase) {
    return NextResponse.json({ status: "queued", source: "mock" });
  }

  // Read the current run from Supabase.
  const { data, error } = await supabase
    .from("sandbox_runs")
    .select(RUN_COLUMNS_WITH_WORKFLOW)
    .eq("id", id)
    .maybeSingle();

  if (error) return NextResponse.json({ detail: error.message }, { status: 500 });
  if (!data) return NextResponse.json({ detail: "Run not found." }, { status: 404 });

  const run = rowToRun(data as unknown as RunRow);

  // Already in a terminal state — return immediately, no backend poll needed.
  if (TERMINAL.has(run.status)) {
    return NextResponse.json({ run, synced: false, source: "supabase" });
  }

  // Still active — ask the backend runner store for an update.
  const session = await getBackendSession(request);
  if (!session.accessToken) {
    return NextResponse.json({ run, synced: false, source: "supabase" });
  }

  let runnerData: RunnerStatus;
  try {
    runnerData = await backendFetch<RunnerStatus>(
      `/api/sandbox/run-status?workflow_id=${encodeURIComponent(id)}`,
      undefined,
      request,
    );
  } catch {
    // Backend unreachable — return what Supabase has, client will retry.
    return NextResponse.json({ run, synced: false, source: "supabase" });
  }

  if (!runnerData.found || !runnerData.status || !TERMINAL.has(STATUS_MAP[runnerData.status] ?? "")) {
    // Still running on the backend side.
    return NextResponse.json({ run, synced: false, source: "supabase" });
  }

  // Runner finished — write the result into Supabase.
  const finalStatus = STATUS_MAP[runnerData.status] ?? "failed";
  const { data: updated, error: updateError } = await supabase
    .from("sandbox_runs")
    .update({
      status: finalStatus,
      verdict: runnerData.verdict ?? null,
      error: runnerData.error ?? null,
      finished_at: runnerData.finished_at ?? new Date().toISOString(),
    })
    .eq("id", id)
    .select(RUN_COLUMNS_WITH_WORKFLOW)
    .single();

  if (updateError || !updated) {
    return NextResponse.json({ run, synced: false, source: "supabase" });
  }

  return NextResponse.json({ run: rowToRun(updated as unknown as RunRow), synced: true, source: "supabase" });
}
