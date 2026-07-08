import { NextResponse } from "next/server";

import { getServerSupabase } from "@/lib/server/supabase";
import {
  canonicalRowToWorkflow,
  CANONICAL_WORKFLOW_COLUMNS,
  LEGACY_WORKFLOW_COLUMNS,
  rowToWorkflow,
  WORKFLOW_COLUMNS,
  type CanonicalWorkflowRow,
  type WorkflowRow,
} from "@/lib/server/workflow-map";
import { mockWorkflows } from "@/lib/mock-data";

export async function GET() {
  const supabase = await getServerSupabase();
  if (!supabase) {
    return NextResponse.json({ workflows: mockWorkflows, source: "mock" });
  }
  const canonical = await supabase
    .from("workflows")
    .select(CANONICAL_WORKFLOW_COLUMNS)
    .order("created_at", { ascending: false });
  if (!canonical.error && canonical.data) {
    return NextResponse.json({
      workflows: (canonical.data as unknown as CanonicalWorkflowRow[]).map(canonicalRowToWorkflow),
      source: "supabase",
    });
  }

  const current = await supabase
    .from("sandbox_workflows")
    .select(WORKFLOW_COLUMNS)
    .order("created_at", { ascending: false });
  let data = current.data as unknown as WorkflowRow[] | null;
  let error = current.error;
  if (error) {
    const legacy = await supabase
      .from("sandbox_workflows")
      .select(LEGACY_WORKFLOW_COLUMNS)
      .order("created_at", { ascending: false });
    data = legacy.data as unknown as WorkflowRow[] | null;
    error = legacy.error;
  }
  if (error) {
    return NextResponse.json({ workflows: mockWorkflows, source: "mock" });
  }
  return NextResponse.json({
    workflows: (data as WorkflowRow[]).map(rowToWorkflow),
    source: "supabase",
  });
}
