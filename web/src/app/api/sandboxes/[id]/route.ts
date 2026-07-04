import { NextResponse } from "next/server";
import { NextRequest } from "next/server";

import { getServerSupabase } from "@/lib/server/supabase";
import { rowToSandbox, SANDBOX_COLUMNS, type SandboxRow } from "@/lib/server/sandbox-map";
import { initialSandboxes, twinOptions } from "@/lib/mock-data";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const supabase = await getServerSupabase();
  if (!supabase) {
    const sandbox = initialSandboxes.find((item) => item.id === id);
    if (!sandbox) {
      return NextResponse.json({ detail: "Sandbox not found." }, { status: 404 });
    }
    return NextResponse.json({ sandbox, source: "mock" });
  }

  const { data, error } = await supabase
    .from("sandboxes")
    .select(SANDBOX_COLUMNS)
    .eq("id", id)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json({ detail: "Sandbox not found." }, { status: 404 });
  }
  return NextResponse.json({ sandbox: rowToSandbox(data as SandboxRow), source: "supabase" });
}

export async function PATCH(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json()) as { twins?: Record<string, string> };
  const twins = body.twins ?? {};

  const validTwinIds = new Set(twinOptions.map((twin) => twin.id));
  const sanitized = Object.fromEntries(
    Object.entries(twins)
      .filter(([twinId, version]) => validTwinIds.has(twinId) && typeof version === "string")
      .map(([twinId, version]) => [twinId, version.trim()]),
  );

  const supabase = await getServerSupabase();
  if (!supabase) {
    const sandbox = initialSandboxes.find((item) => item.id === id);
    if (!sandbox) {
      return NextResponse.json({ detail: "Sandbox not found." }, { status: 404 });
    }
    return NextResponse.json({
      sandbox: {
        ...sandbox,
        twins: Object.keys(sanitized).map(
          (twinId) => twinOptions.find((twin) => twin.id === twinId)?.name ?? twinId,
        ),
        twinVersions: sanitized,
      },
      source: "mock",
    });
  }

  const { data, error } = await supabase
    .from("sandboxes")
    .update({ twins: sanitized })
    .eq("id", id)
    .select(SANDBOX_COLUMNS)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json({ detail: "Sandbox not found." }, { status: 404 });
  }
  return NextResponse.json({ sandbox: rowToSandbox(data as SandboxRow), source: "supabase" });
}
