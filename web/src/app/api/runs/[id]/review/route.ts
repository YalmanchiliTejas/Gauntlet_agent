import { NextResponse } from "next/server";

import { getServerSupabase } from "@/lib/server/supabase";
import { reviewTrace } from "@/lib/server/review";
import { rowToRun, RUN_COLUMNS_WITH_WORKFLOW, type RunRow } from "@/lib/server/workflow-map";
import { mockRuns } from "@/lib/mock-data";
import type { TraceStep } from "@/lib/sandbox-api";

// The judge reviews this run's trace (any status) and tags steps with
// inefficiencies / possible fixes.
export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const supabase = await getServerSupabase();
  if (!supabase) {
    const run = mockRuns.find((item) => item.id === id);
    if (!run) return NextResponse.json({ detail: "Run not found." }, { status: 404 });
    const review = await reviewTrace(run.trajectory as TraceStep[]);
    return NextResponse.json({ run: { ...run, review }, source: "mock" });
  }

  const { data: row, error: findError } = await supabase
    .from("sandbox_runs")
    .select("trajectory")
    .eq("id", id)
    .maybeSingle();
  if (findError) return NextResponse.json({ detail: findError.message }, { status: 500 });
  if (!row) return NextResponse.json({ detail: "Run not found." }, { status: 404 });

  const trajectory = Array.isArray((row as { trajectory: unknown }).trajectory)
    ? ((row as { trajectory: TraceStep[] }).trajectory)
    : [];
  const review = await reviewTrace(trajectory);

  const { data, error } = await supabase
    .from("sandbox_runs")
    .update({ review })
    .eq("id", id)
    .select(RUN_COLUMNS_WITH_WORKFLOW)
    .single();
  if (error || !data) {
    return NextResponse.json({ detail: error?.message ?? "Could not save review." }, { status: 500 });
  }
  return NextResponse.json({ run: rowToRun(data as unknown as RunRow), source: "supabase" });
}
