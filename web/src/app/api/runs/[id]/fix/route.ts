import { NextResponse } from "next/server";

import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";
import { rowToRun, RUN_COLUMNS_WITH_WORKFLOW, type RunRow } from "@/lib/server/workflow-map";

// The "fix" button: spawn a fix attempt off an existing (usually failed) run.
// Creates a new queued run linked back via fix_of.
export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
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
    .select("sandbox_id, workflow_id")
    .eq("id", id)
    .maybeSingle();
  if (findError) return NextResponse.json({ detail: findError.message }, { status: 500 });
  if (!source) return NextResponse.json({ detail: "Run not found." }, { status: 404 });

  const { data, error } = await supabase
    .from("sandbox_runs")
    .insert({
      sandbox_id: (source as { sandbox_id: string }).sandbox_id,
      workflow_id: (source as { workflow_id: string | null }).workflow_id,
      fix_of: id,
      status: "queued",
    })
    .select(RUN_COLUMNS_WITH_WORKFLOW)
    .single();
  if (error || !data) {
    return NextResponse.json({ detail: error?.message ?? "Could not start fix." }, { status: 500 });
  }
  return NextResponse.json({ run: rowToRun(data as unknown as RunRow), source: "supabase" }, { status: 201 });
}
