import { NextResponse } from "next/server";

import { getServerSupabase } from "@/lib/server/supabase";
import { rowToRun, RUN_COLUMNS_WITH_WORKFLOW, type RunRow } from "@/lib/server/workflow-map";
import { mockRuns } from "@/lib/mock-data";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await getServerSupabase();
  if (!supabase) {
    const run = mockRuns.find((item) => item.id === id);
    if (!run) return NextResponse.json({ detail: "Run not found." }, { status: 404 });
    return NextResponse.json({ run, source: "mock" });
  }
  const { data, error } = await supabase
    .from("sandbox_runs")
    .select(RUN_COLUMNS_WITH_WORKFLOW)
    .eq("id", id)
    .maybeSingle();
  if (error) return NextResponse.json({ detail: error.message }, { status: 500 });
  if (!data) return NextResponse.json({ detail: "Run not found." }, { status: 404 });
  return NextResponse.json({ run: rowToRun(data as unknown as RunRow), source: "supabase" });
}
