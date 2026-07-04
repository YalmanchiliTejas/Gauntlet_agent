import { NextRequest, NextResponse } from "next/server";

import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";
import { rowToRun, RUN_COLUMNS_WITH_WORKFLOW, type RunRow } from "@/lib/server/workflow-map";
import { mockRuns } from "@/lib/mock-data";

type ActiveScenarioRow = {
  id: string;
  seed: Record<string, unknown>;
};

type EnvKeyRow = {
  key: string;
};

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

  const { data: scenario } = await supabase
    .from("sandbox_scenarios")
    .select("id, seed")
    .eq("sandbox_id", id)
    .eq("is_active", true)
    .maybeSingle();
  const activeScenario = scenario as ActiveScenarioRow | null;
  const { data: envRows } = await supabase
    .from("sandbox_env_vars")
    .select("key")
    .eq("sandbox_id", id)
    .order("key", { ascending: true });
  const envKeys = ((envRows as EnvKeyRow[] | null) ?? []).map((row) => row.key);

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
  return NextResponse.json({ run: rowToRun(data as unknown as RunRow), source: "supabase" }, { status: 201 });
}
