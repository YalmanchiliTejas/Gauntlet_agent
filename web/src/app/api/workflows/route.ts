import { NextResponse } from "next/server";

import { getServerSupabase } from "@/lib/server/supabase";
import { rowToWorkflow, WORKFLOW_COLUMNS, type WorkflowRow } from "@/lib/server/workflow-map";
import { mockWorkflows } from "@/lib/mock-data";

export async function GET() {
  const supabase = await getServerSupabase();
  if (!supabase) {
    return NextResponse.json({ workflows: mockWorkflows, source: "mock" });
  }
  const { data, error } = await supabase
    .from("sandbox_workflows")
    .select(WORKFLOW_COLUMNS)
    .order("created_at", { ascending: false });
  if (error) {
    return NextResponse.json({ workflows: mockWorkflows, source: "mock" });
  }
  return NextResponse.json({
    workflows: (data as WorkflowRow[]).map(rowToWorkflow),
    source: "supabase",
  });
}
