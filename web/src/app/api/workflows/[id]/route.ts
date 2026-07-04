import { NextRequest, NextResponse } from "next/server";

import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";
import { mockWorkflows } from "@/lib/mock-data";
import {
  canonicalRowToWorkflow,
  CANONICAL_WORKFLOW_COLUMNS,
  rowToWorkflow,
  WORKFLOW_COLUMNS,
  type CanonicalWorkflowRow,
  type WorkflowRow,
} from "@/lib/server/workflow-map";
import { workflowFingerprint } from "@/lib/server/workflow-dedupe";

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json()) as {
    name?: string;
    description?: string | null;
    difficulty?: string | null;
    taskPrompt?: string | null;
    services?: string[];
  };

  const name = body.name?.trim();
  if (!name) {
    return NextResponse.json({ detail: "Workflow name is required." }, { status: 400 });
  }

  const patch = {
    name,
    description: body.description?.trim() || null,
    difficulty: body.difficulty?.trim() || null,
    task_prompt: body.taskPrompt?.trim() || null,
    draft: {
      services: Array.isArray(body.services)
        ? body.services.map((service) => service.trim()).filter(Boolean)
        : [],
    },
  };

  const supabase = await getServerSupabase();
  if (!supabase) {
    if (!isDevBypass()) {
      return NextResponse.json({ detail: "Sign in to edit workflows." }, { status: 401 });
    }
    const existing = mockWorkflows.find((workflow) => workflow.id === id);
    if (!existing) {
      return NextResponse.json({ detail: "Workflow not found." }, { status: 404 });
    }
    return NextResponse.json({
      workflow: {
        ...existing,
        name: patch.name,
        description: patch.description,
        difficulty: patch.difficulty,
        taskPrompt: patch.task_prompt,
        services: patch.draft.services,
      },
      source: "dev-bypass",
    });
  }

  const canonicalPatch = {
    ...patch,
    fingerprint: workflowFingerprint(patch),
    updated_at: new Date().toISOString(),
  };
  const canonical = await supabase
    .from("workflows")
    .update(canonicalPatch)
    .eq("id", id)
    .select(CANONICAL_WORKFLOW_COLUMNS)
    .maybeSingle();
  if (!canonical.error && canonical.data) {
    return NextResponse.json({
      workflow: canonicalRowToWorkflow(canonical.data as unknown as CanonicalWorkflowRow),
      source: "supabase",
    });
  }

  const { data, error } = await supabase
    .from("sandbox_workflows")
    .update(patch)
    .eq("id", id)
    .select(WORKFLOW_COLUMNS)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json({ detail: "Workflow not found." }, { status: 404 });
  }
  return NextResponse.json({ workflow: rowToWorkflow(data as WorkflowRow), source: "supabase" });
}

export async function DELETE(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await getServerSupabase();
  if (!supabase) {
    if (!isDevBypass()) {
      return NextResponse.json({ detail: "Sign in to delete workflows." }, { status: 401 });
    }
    return NextResponse.json({ ok: true, source: "dev-bypass" });
  }

  const canonicalDelete = await supabase.from("workflows").delete().eq("id", id);
  if (!canonicalDelete.error) {
    return NextResponse.json({ ok: true, source: "supabase" });
  }

  const { error } = await supabase.from("sandbox_workflows").delete().eq("id", id);
  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, source: "supabase" });
}
