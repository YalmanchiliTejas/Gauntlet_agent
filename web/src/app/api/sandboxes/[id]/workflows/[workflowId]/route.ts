import { NextResponse } from "next/server";

import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string; workflowId: string }> },
) {
  const { id, workflowId } = await params;
  const supabase = await getServerSupabase();
  if (!supabase) {
    if (!isDevBypass()) {
      return NextResponse.json({ detail: "Sign in to remove workflows from sandboxes." }, { status: 401 });
    }
    return NextResponse.json({ ok: true, source: "dev-bypass" });
  }

  const byCanonical = await supabase
    .from("sandbox_workflows")
    .delete()
    .eq("sandbox_id", id)
    .eq("workflow_id", workflowId);

  if (byCanonical.error) {
    return NextResponse.json({ detail: byCanonical.error.message }, { status: 500 });
  }

  const byAssignment = await supabase
    .from("sandbox_workflows")
    .delete()
    .eq("sandbox_id", id)
    .eq("id", workflowId);

  if (byAssignment.error) {
    return NextResponse.json({ detail: byAssignment.error.message }, { status: 500 });
  }

  return NextResponse.json({ ok: true, source: "supabase" });
}
