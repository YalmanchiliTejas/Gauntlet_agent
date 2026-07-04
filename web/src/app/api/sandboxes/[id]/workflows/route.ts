import { NextRequest, NextResponse } from "next/server";

import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";
import { generateDrafts } from "@/lib/server/generate";
import {
  LEGACY_WORKFLOW_COLUMNS,
  rowToWorkflow,
  WORKFLOW_COLUMNS,
  type WorkflowRow,
} from "@/lib/server/workflow-map";
import { filterNovelDrafts, workflowFingerprint } from "@/lib/server/workflow-dedupe";
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
  const current = await supabase
    .from("sandbox_workflows")
    .select(WORKFLOW_COLUMNS)
    .eq("sandbox_id", id)
    .order("created_at", { ascending: false });
  let data = current.data as unknown as WorkflowRow[] | null;
  let error = current.error;
  if (error) {
    const legacy = await supabase
      .from("sandbox_workflows")
      .select(LEGACY_WORKFLOW_COLUMNS)
      .eq("sandbox_id", id)
      .order("created_at", { ascending: false });
    data = legacy.data as unknown as WorkflowRow[] | null;
    error = legacy.error;
  }
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
    focus?: string;
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

  const supabase = await getServerSupabase();
  if (!supabase) {
    if (!isDevBypass()) {
      return NextResponse.json(
        { detail: "Sign in to generate and save workflows." },
        { status: 401 },
      );
    }
    const drafts = await generateDrafts({
      docs,
      services,
      count,
      workflowName: body.workflowName,
      focus: body.focus,
    });
    // Dev bypass only: return the drafts without persisting.
    return NextResponse.json({
      workflows: drafts.map((draft, index) => ({
        id: `wf_local_${Date.now()}_${index}`,
        sandboxId: id,
        canonicalId: `wf_local_${Date.now()}_${index}`,
        name: draft.name,
        description: draft.description,
        difficulty: draft.difficulty,
        taskPrompt: draft.task_prompt,
        services: services.map((s) => s.name),
        focus: body.focus?.trim() || null,
        noveltyReason: "Dev bypass draft; persistence and duplicate checks were skipped.",
        createdAt: new Date().toISOString(),
      })),
      source: "dev-bypass",
    });
  }

  const currentExisting = await supabase
    .from("sandbox_workflows")
    .select(WORKFLOW_COLUMNS)
    .eq("sandbox_id", id)
    .order("created_at", { ascending: false });
  let existingRows = currentExisting.data as unknown as WorkflowRow[] | null;
  let existingError = currentExisting.error;
  if (existingError) {
    const legacy = await supabase
      .from("sandbox_workflows")
      .select(LEGACY_WORKFLOW_COLUMNS)
      .eq("sandbox_id", id)
      .order("created_at", { ascending: false });
    existingRows = legacy.data as unknown as WorkflowRow[] | null;
    existingError = legacy.error;
  }
  if (existingError) {
    return NextResponse.json({ detail: existingError.message }, { status: 500 });
  }

  const existing = (existingRows ?? []) as WorkflowRow[];
  const candidateCount = Math.min(Math.max(count * 3, count + 6), 36);
  const drafts = await generateDrafts({
    docs,
    services,
    count: candidateCount,
    workflowName: body.workflowName,
    focus: body.focus,
    existingWorkflows: existing.map((row) => ({
      name: (Array.isArray(row.workflows) ? row.workflows[0] : row.workflows)?.name ?? row.name,
      description:
        (Array.isArray(row.workflows) ? row.workflows[0] : row.workflows)?.description ?? row.description,
      task_prompt:
        (Array.isArray(row.workflows) ? row.workflows[0] : row.workflows)?.task_prompt ?? row.task_prompt,
      draft: ((Array.isArray(row.workflows) ? row.workflows[0] : row.workflows)?.draft ?? row.draft ?? {}) as Record<string, unknown>,
    })),
  });
  const novel = filterNovelDrafts(drafts, existing);
  const accepted = novel.accepted.slice(0, count);
  const skipped = novel.skipped;

  if (accepted.length === 0) {
    return NextResponse.json({
      workflows: [],
      skipped,
      source: "supabase",
      detail: "No novel workflows were generated for this sandbox.",
    }, { status: 409 });
  }

  const canonicalRows = accepted.map((draft) => ({
    source_sandbox_id: id,
    name: draft.name,
    description: draft.description,
    difficulty: draft.difficulty,
    task_prompt: draft.task_prompt,
    draft: {
      ...draft.draft,
      focus: body.focus?.trim() || draft.draft.focus || null,
    },
    focus: body.focus?.trim() || null,
    fingerprint: workflowFingerprint(draft),
  }));

  const { data: workflowRows, error: workflowError } = await supabase
    .from("workflows")
    .insert(canonicalRows)
    .select("id, name, description, difficulty, task_prompt, draft");
  if (workflowError || !workflowRows) {
    return NextResponse.json(
      { detail: workflowError?.message ?? "Could not save generated workflows." },
      { status: 500 },
    );
  }

  const assignmentRows = workflowRows.map((workflow, index) => {
    const draft = accepted[index];
    return {
      sandbox_id: id,
      workflow_id: workflow.id,
      name: draft.name,
      description: draft.description,
      difficulty: draft.difficulty,
      task_prompt: draft.task_prompt,
      draft: draft.draft,
      assignment_metadata: {
        source: "generated",
        focus: body.focus?.trim() || null,
      },
    };
  });
  const { data, error } = await supabase
    .from("sandbox_workflows")
    .insert(assignmentRows)
    .select(WORKFLOW_COLUMNS);
  if (error || !data) {
    return NextResponse.json({ detail: error?.message ?? "Could not assign workflows." }, { status: 500 });
  }
  return NextResponse.json({
    workflows: (data as unknown as WorkflowRow[]).map(rowToWorkflow),
    skipped,
    detail:
      accepted.length < count
        ? `Generated ${accepted.length} novel workflow${accepted.length === 1 ? "" : "s"} after filtering duplicates.`
        : undefined,
    source: "supabase",
  });
}
