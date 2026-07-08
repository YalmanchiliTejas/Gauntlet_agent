import { NextRequest, NextResponse } from "next/server";

import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";

type EnvRow = {
  key: string;
  updated_at: string;
};

const ENV_COLUMNS = "key, updated_at";
const KEY_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await getServerSupabase();
  if (!supabase) {
    return NextResponse.json({ env: [], source: isDevBypass() ? "dev-bypass" : "mock" });
  }

  const { data, error } = await supabase
    .from("sandbox_env_vars")
    .select(ENV_COLUMNS)
    .eq("sandbox_id", id)
    .order("key", { ascending: true });
  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 500 });
  }
  return NextResponse.json({ env: (data as EnvRow[]).map(rowToEnvVar), source: "supabase" });
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as {
    env?: { key?: string; value?: string }[];
  };
  const env = (body.env ?? [])
    .map((item) => ({ key: item.key?.trim() ?? "", value: item.value ?? "" }))
    .filter((item) => item.key || item.value);

  const invalid = env.find((item) => !KEY_PATTERN.test(item.key));
  if (invalid) {
    return NextResponse.json(
      { detail: `Invalid env var key: ${invalid.key || "(empty)"}.` },
      { status: 400 },
    );
  }
  const missingValue = env.find((item) => item.value.length === 0);
  if (missingValue) {
    return NextResponse.json(
      { detail: `Add a value for ${missingValue.key}; values are not shown after saving.` },
      { status: 400 },
    );
  }

  const supabase = await getServerSupabase();
  if (!supabase) {
    if (!isDevBypass()) {
      return NextResponse.json({ detail: "Sign in to save environment variables." }, { status: 401 });
    }
    return NextResponse.json({
      env: env.map((item) => ({ key: item.key, updatedAt: new Date().toISOString() })),
      source: "dev-bypass",
    });
  }

  const now = new Date().toISOString();
  const rows = env.map((item) => ({
    sandbox_id: id,
    key: item.key,
    value: item.value,
    updated_at: now,
  }));

  const { data, error } = await supabase
    .from("sandbox_env_vars")
    .upsert(rows, { onConflict: "sandbox_id,key" })
    .select(ENV_COLUMNS)
    .order("key", { ascending: true });
  if (error || !data) {
    return NextResponse.json({ detail: error?.message ?? "Could not save env vars." }, { status: 500 });
  }
  return NextResponse.json({ env: (data as EnvRow[]).map(rowToEnvVar), source: "supabase" });
}

export async function DELETE(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const key = new URL(request.url).searchParams.get("key")?.trim();
  if (!key) {
    return NextResponse.json({ detail: "key is required." }, { status: 400 });
  }

  const supabase = await getServerSupabase();
  if (!supabase) {
    if (!isDevBypass()) {
      return NextResponse.json({ detail: "Sign in to delete environment variables." }, { status: 401 });
    }
    return NextResponse.json({ ok: true, source: "dev-bypass" });
  }

  const { error } = await supabase
    .from("sandbox_env_vars")
    .delete()
    .eq("sandbox_id", id)
    .eq("key", key);
  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, source: "supabase" });
}

function rowToEnvVar(row: EnvRow) {
  return {
    key: row.key,
    updatedAt: row.updated_at,
  };
}
