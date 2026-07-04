import { NextRequest, NextResponse } from "next/server";

import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";
import { generateDrafts } from "@/lib/server/generate";
import { rowToWorkflow, WORKFLOW_COLUMNS, type WorkflowRow } from "@/lib/server/workflow-map";
import { mockWorkflows } from "@/lib/mock-data";
import type { DocInput } from "@/lib/sandbox-api";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await getServerSupabase();
  if (!supabase) {
    return NextResponse.json({
      workflows: mockWorkflows.filter((wf) => wf.sandboxId === id),
      source: "mock",
    });
  }
  const { data, error } = await supabase
    .from("sandbox_workflows")
    .select(WORKFLOW_COLUMNS)
    .eq("sandbox_id", id)
    .order("created_at", { ascending: false });
  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 500 });
  }
  return NextResponse.json({
    workflows: (data as WorkflowRow[]).map(rowToWorkflow),
    source: "supabase",
  });
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json()) as {
    workflowName?: string;
    docs?: DocInput[];
    services?: { name: string; version?: string | null }[];
    count?: number;
  };

  const docs = (body.docs ?? []).filter((doc) => doc.title?.trim() && doc.text?.trim());
  if (docs.length === 0) {
    return NextResponse.json(
      { detail: "Add at least one doc (title + text) to generate workflows." },
      { status: 400 },
    );
  }
  const services = body.services ?? [];
  const count = Math.min(Math.max(body.count ?? docs.length, 1), 12);

  const drafts = await generateDrafts({ docs, services, count, workflowName: body.workflowName });

  const supabase = await getServerSupabase();
  if (!supabase) {
    if (!isDevBypass()) {
      return NextResponse.json(
        { detail: "Sign in to generate and save workflows." },
        { status: 401 },
      );
    }
    // Dev bypass only: return the drafts without persisting.
    return NextResponse.json({
      workflows: drafts.map((draft, index) => ({
        id: `wf_local_${Date.now()}_${index}`,
        sandboxId: id,
        name: draft.name,
        description: draft.description,
        difficulty: draft.difficulty,
        taskPrompt: draft.task_prompt,
        services: services.map((s) => s.name),
        createdAt: new Date().toISOString(),
      })),
      source: "dev-bypass",
    });
  }

  const { data, error } = await supabase
    .from("sandbox_workflows")
    .insert(drafts.map((draft) => ({ ...draft, sandbox_id: id })))
    .select(WORKFLOW_COLUMNS);
  if (error || !data) {
    return NextResponse.json({ detail: error?.message ?? "Could not save workflows." }, { status: 500 });
  }
  return NextResponse.json({
    workflows: (data as WorkflowRow[]).map(rowToWorkflow),
    source: "supabase",
  });
}
