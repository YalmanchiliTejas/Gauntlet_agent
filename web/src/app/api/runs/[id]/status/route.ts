import { NextRequest, NextResponse } from "next/server";

import { getBackendSession } from "@/lib/server/gauntlet-backend";
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

const ORPHANED_RUN_TIMEOUT_MS = 20 * 60 * 1000;

type RunnerStatus = {
  found: boolean;
  status?: string;
  verdict?: Record<string, unknown> | null;
  trajectory?: unknown;
  error?: string | null;
  exit_code?: number | null;
  finished_at?: string | null;
};

function normalizeTrajectory(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (typeof value !== "string") return [];

  const text = value.trim();
  if (!text) return [];

  try {
    const parsed = JSON.parse(text) as unknown;
    if (Array.isArray(parsed)) return parsed;
  } catch {
    // Native traces are often JSONL, not a single JSON array.
  }

  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line) as unknown;
      } catch {
        return null;
      }
    })
    .filter((step): step is unknown => step !== null);
}

function isOrphanedQueuedRun(createdAt: string): boolean {
  const created = Date.parse(createdAt);
  return Number.isFinite(created) && Date.now() - created > ORPHANED_RUN_TIMEOUT_MS;
}

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

  // Already in a terminal state with a stored trace — return immediately, no backend poll needed.
  // Terminal rows with an empty trace may be older partial syncs, so allow one backend refresh.
  if (TERMINAL.has(run.status) && run.trajectory.length > 0) {
    return NextResponse.json({ run, synced: false, source: "supabase" });
  }

  // Still active — ask the backend for an update. /run-status is unauthenticated, so poll
  // it directly instead of through the bearer-gated backendFetch: the server-side session
  // token is unreliable and isn't needed here, and gating on it left runs stuck at "queued".
  const session = await getBackendSession(request);
  let runnerData: RunnerStatus;
  try {
    const res = await fetch(
      `${session.apiUrl}/api/sandbox/run-status?workflow_id=${encodeURIComponent(id)}`,
      { cache: "no-store" },
    );
    if (!res.ok) throw new Error(`run-status ${res.status}`);
    runnerData = (await res.json()) as RunnerStatus;
  } catch {
    // Backend unreachable — return what Supabase has, client will retry.
    return NextResponse.json({ run, synced: false, source: "supabase" });
  }

  const normalizedTrajectory = normalizeTrajectory(runnerData.trajectory);

  if (!runnerData.found) {
    if (run.status === "queued" && isOrphanedQueuedRun(run.createdAt)) {
      const { data: updated, error: updateError } = await supabase
        .from("sandbox_runs")
        .update({
          status: "error",
          error: "Run was never accepted by the sandbox backend. Start a new run after reconnecting backend auth.",
          finished_at: new Date().toISOString(),
        })
        .eq("id", id)
        .select(RUN_COLUMNS_WITH_WORKFLOW)
        .single();

      if (!updateError && updated) {
        return NextResponse.json({ run: rowToRun(updated as unknown as RunRow), synced: true, source: "supabase" });
      }
    }
    return NextResponse.json({ run, synced: false, source: "supabase" });
  }

  if (!runnerData.status || !TERMINAL.has(STATUS_MAP[runnerData.status] ?? "")) {
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
      trajectory: normalizedTrajectory,
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
