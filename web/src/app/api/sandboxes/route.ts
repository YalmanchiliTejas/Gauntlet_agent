import { NextRequest, NextResponse } from "next/server";

import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";
import { rowToSandbox, SANDBOX_COLUMNS, type SandboxRow } from "@/lib/server/sandbox-map";
import { initialSandboxes, twinOptions, type Sandbox } from "@/lib/mock-data";

function humanizeRepoName(repoName: string) {
  const label = repoName.replace(/[-_]+/g, " ").replace(/\bagent\b/i, "agent").trim();
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export async function GET() {
  const supabase = await getServerSupabase();
  if (!supabase) {
    return NextResponse.json({ sandboxes: initialSandboxes, source: "mock" });
  }

  const { data, error } = await supabase
    .from("sandboxes")
    .select(SANDBOX_COLUMNS)
    .order("created_at", { ascending: false });

  if (error) {
    return NextResponse.json({ sandboxes: initialSandboxes, source: "mock" });
  }
  return NextResponse.json({
    sandboxes: (data as SandboxRow[]).map(rowToSandbox),
    source: "supabase",
  });
}

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    name?: string;
    repo?: string;
    branch?: string;
    twins?: Record<string, string>;
  };

  if (!body.repo || !body.branch) {
    return NextResponse.json({ detail: "repo and branch are required." }, { status: 400 });
  }

  const repoName = body.repo.split("/").pop() ?? "agent";
  const name = body.name?.trim() || humanizeRepoName(repoName);
  const twins = body.twins ?? {};

  const supabase = await getServerSupabase();
  if (!supabase) {
    const supabaseConfigured =
      Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL) &&
      Boolean(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);

    // Can't persist (signed-out / Supabase not configured). Only stub in explicit
    // dev bypass when there is no Supabase project configured; otherwise fail
    // loudly so the client never thinks it was stored.
    if (!isDevBypass() || supabaseConfigured) {
      return NextResponse.json(
        { detail: "Sign in to create a sandbox — it can only be stored for an authenticated user." },
        { status: 401 },
      );
    }
    const sandbox: Sandbox = {
      id: `sandbox_${Date.now()}`,
      name,
      repo: body.repo,
      branch: body.branch,
      status: "Ready",
      twins: Object.keys(twins).map(
        (id) => twinOptions.find((twin) => twin.id === id)?.name ?? id,
      ),
      workflowCount: 0,
      lastRun: "Never run",
    };
    return NextResponse.json({ sandbox, source: "dev-bypass" }, { status: 201 });
  }

  // user_id defaults to auth.uid() via the column default; RLS enforces ownership.
  const { data, error } = await supabase
    .from("sandboxes")
    .insert({ name, repo: body.repo, branch: body.branch, twins })
    .select(SANDBOX_COLUMNS)
    .single();

  if (error || !data) {
    return NextResponse.json({ detail: error?.message ?? "Could not create sandbox." }, { status: 500 });
  }
  return NextResponse.json(
    { sandbox: rowToSandbox(data as SandboxRow), source: "supabase" },
    { status: 201 },
  );
}
