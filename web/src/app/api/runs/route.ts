import { NextResponse } from "next/server";

import { getServerSupabase } from "@/lib/server/supabase";
import { rowToRun, RUN_COLUMNS_WITH_WORKFLOW, type RunRow } from "@/lib/server/workflow-map";
import { mockRuns } from "@/lib/mock-data";

export async function GET() {
  const supabase = await getServerSupabase();
  if (!supabase) {
    return NextResponse.json({ runs: mockRuns, source: "mock" });
  }
  const { data, error } = await supabase
    .from("sandbox_runs")
    .select(RUN_COLUMNS_WITH_WORKFLOW)
    .order("created_at", { ascending: false });
  if (error) {
    return NextResponse.json({ runs: mockRuns, source: "mock" });
  }
  return NextResponse.json({ runs: (data as unknown as RunRow[]).map(rowToRun), source: "supabase" });
}
