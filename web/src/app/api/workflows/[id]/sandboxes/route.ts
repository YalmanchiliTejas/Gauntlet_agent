import { NextRequest, NextResponse } from "next/server";

import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";
import { rowToWorkflow, WORKFLOW_COLUMNS, type CanonicalWorkflowRow, type WorkflowRow } from "@/lib/server/workflow-map";

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as {
    sandboxIds?: string[];
  };
  const sandboxIds = Array.from(
    new Set((body.sandboxIds ?? []).map((sandboxId) => sandboxId.trim()).filter(Boolean)),
  );

  if (sandboxIds.length === 0) {
    return NextResponse.json({ detail: "Select at least one sandbox." }, { status: 400 });
  }

  const supabase = await getServerSupabase();
  if (!supabase) {
    if (!isDevBypass()) {
      return NextResponse.json({ detail: "Sign in to assign workflows." }, { status: 401 });
    }
    return NextResponse.json({ workflows: [], source: "dev-bypass" });
  }

  const { data: workflow, error: workflowError } = await supabase
    .from("workflows")
    .select("id, name, description, difficulty, task_prompt, draft")
    .eq("id", id)
    .maybeSingle();

  if (workflowError) {
    return NextResponse.json({ detail: workflowError.message }, { status: 500 });
  }
  if (!workflow) {
    return NextResponse.json({ detail: "Workflow not found." }, { status: 404 });
  }

  const canonical = workflow as CanonicalWorkflowRow;
  const rows = sandboxIds.map((sandboxId) => ({
    sandbox_id: sandboxId,
    workflow_id: canonical.id,
    name: canonical.name,
    description: canonical.description,
    difficulty: canonical.difficulty,
    task_prompt: canonical.task_prompt,
    draft: canonical.draft ?? {},
    assignment_metadata: { source: "manual_assignment" },
  }));

  const { data, error } = await supabase
    .from("sandbox_workflows")
    .upsert(rows, { onConflict: "sandbox_id,workflow_id", ignoreDuplicates: true })
    .select(WORKFLOW_COLUMNS);

  if (error || !data) {
    return NextResponse.json({ detail: error?.message ?? "Could not assign workflow." }, { status: 500 });
  }

  return NextResponse.json({
    workflows: (data as WorkflowRow[]).map(rowToWorkflow),
    source: "supabase",
  });
}
