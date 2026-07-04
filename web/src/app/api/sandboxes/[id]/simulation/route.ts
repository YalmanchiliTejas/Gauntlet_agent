import { readFile } from "node:fs/promises";
import path from "node:path";

import { NextRequest, NextResponse } from "next/server";

import { initialSandboxes, twinOptions } from "@/lib/mock-data";
import { rowToSandbox, SANDBOX_COLUMNS, type SandboxRow } from "@/lib/server/sandbox-map";
import { getServerSupabase } from "@/lib/server/supabase";

type Profile = "baseline" | "busy" | "edge";
type SeedRecords = Record<string, Array<Record<string, unknown>>>;
type ScenarioSeed = {
  service: string;
  version: string;
  resources: SeedRecords;
};
type ScenarioPayload = {
  id?: string | null;
  sandboxId: string;
  name?: string;
  profile: Profile;
  generatedAt: string;
  seeds: ScenarioSeed[];
};
type ScenarioRow = {
  id: string;
  sandbox_id: string;
  name: string;
  profile: Profile;
  seed: ScenarioPayload;
  updated_at: string;
};

const registryRoot = path.resolve(process.cwd(), "..", "twins", "registry");
const SCENARIO_COLUMNS = "id, sandbox_id, name, profile, seed, updated_at";

export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const supabase = await getServerSupabase();
  if (!supabase) {
    return NextResponse.json({ scenario: null, source: "mock" });
  }

  const { data, error } = await supabase
    .from("sandbox_scenarios")
    .select(SCENARIO_COLUMNS)
    .eq("sandbox_id", id)
    .eq("is_active", true)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ detail: error.message }, { status: 500 });
  }
  return NextResponse.json({
    scenario: data ? rowToScenario(data as ScenarioRow) : null,
    source: "supabase",
  });
}

export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as { profile?: Profile };
  const profile: Profile = body.profile === "busy" || body.profile === "edge" ? body.profile : "baseline";
  const sandbox = await loadSandbox(id);

  if (!sandbox) {
    return NextResponse.json({ detail: "Sandbox not found." }, { status: 404 });
  }

  const twinVersions =
    sandbox.twinVersions ??
    Object.fromEntries(
      sandbox.twins.map((name) => {
        const twin = twinOptions.find((item) => item.name === name);
        return [twin?.id ?? name, twin?.versions[twin.versions.length - 1] ?? "v1"];
      }),
    );
  const seeds = await Promise.all(
    Object.entries(twinVersions).map(async ([service, version]) => ({
      service,
      version,
      resources: expandSeed(await readSeed(service, version), profile, service),
    })),
  );

  return NextResponse.json({
    scenario: {
      id: null,
      sandboxId: sandbox.id,
      name: `${profileLabel(profile)} scenario`,
      profile,
      generatedAt: new Date().toISOString(),
      seeds,
    },
  });
}

export async function PUT(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as { scenario?: ScenarioPayload };
  const scenario = normalizeScenario(id, body.scenario);
  if (!scenario) {
    return NextResponse.json({ detail: "Valid scenario JSON is required." }, { status: 400 });
  }

  const supabase = await getServerSupabase();
  if (!supabase) {
    return NextResponse.json({ scenario: { ...scenario, id: null }, source: "dev-bypass" });
  }

  const { data: existing, error: readError } = await supabase
    .from("sandbox_scenarios")
    .select("id")
    .eq("sandbox_id", id)
    .eq("is_active", true)
    .maybeSingle();
  if (readError) {
    return NextResponse.json({ detail: readError.message }, { status: 500 });
  }

  const patch = {
    sandbox_id: id,
    name: scenario.name || "Default scenario",
    profile: scenario.profile,
    seed: scenario,
    is_active: true,
    updated_at: new Date().toISOString(),
  };

  const query = existing?.id
    ? supabase.from("sandbox_scenarios").update(patch).eq("id", existing.id)
    : supabase.from("sandbox_scenarios").insert(patch);

  const { data, error } = await query.select(SCENARIO_COLUMNS).single();
  if (error || !data) {
    return NextResponse.json({ detail: error?.message ?? "Could not save scenario." }, { status: 500 });
  }
  return NextResponse.json({ scenario: rowToScenario(data as ScenarioRow), source: "supabase" });
}

async function loadSandbox(id: string) {
  const supabase = await getServerSupabase();
  if (!supabase) {
    return initialSandboxes.find((item) => item.id === id) ?? null;
  }

  const { data, error } = await supabase
    .from("sandboxes")
    .select(SANDBOX_COLUMNS)
    .eq("id", id)
    .maybeSingle();
  if (error || !data) return null;
  return rowToSandbox(data as SandboxRow);
}

async function readSeed(service: string, version: string): Promise<SeedRecords> {
  const safeService = service.replace(/[^a-zA-Z0-9_-]/g, "");
  const safeVersion = version.replace(/[^a-zA-Z0-9_.-]/g, "");
  const file = path.join(registryRoot, safeService, safeVersion, "seed.json");
  const raw = await readFile(file, "utf8").catch(() => "{}");
  const parsed = JSON.parse(raw) as SeedRecords;
  return Object.fromEntries(
    Object.entries(parsed).map(([resource, rows]) => [
      resource,
      Array.isArray(rows) ? rows.filter(isRecord) : [],
    ]),
  );
}

function expandSeed(seed: SeedRecords, profile: Profile, service: string): SeedRecords {
  if (profile === "baseline") return seed;

  const copies = profile === "busy" ? 4 : 2;
  return Object.fromEntries(
    Object.entries(seed).map(([resource, rows]) => [
      resource,
      rows.flatMap((row) =>
        Array.from({ length: copies }, (_, index) =>
          profile === "edge"
            ? edgeRecord(row, index, service, resource)
            : busyRecord(row, index, service, resource),
        ),
      ),
    ]),
  );
}

function busyRecord(
  row: Record<string, unknown>,
  index: number,
  service: string,
  resource: string,
): Record<string, unknown> {
  const id = String(row.id ?? `${service}_${resource}_seed`);
  return {
    ...row,
    id: `${id}_${index + 1}`,
    name: typeof row.name === "string" ? `${row.name} ${index + 1}` : row.name,
    email: typeof row.email === "string" ? withEmailTag(row.email, `busy${index + 1}`) : row.email,
    snippet: typeof row.snippet === "string" ? `${row.snippet} ${index + 1}` : row.snippet,
  };
}

function edgeRecord(
  row: Record<string, unknown>,
  index: number,
  service: string,
  resource: string,
): Record<string, unknown> {
  const id = String(row.id ?? `${service}_${resource}_edge`);
  const variants = [
    {
      ...row,
      id: `${id}_missing_optional`,
      name: "",
      email: typeof row.email === "string" ? withEmailTag(row.email, "missing") : row.email,
    },
    {
      ...row,
      id: `${id}_stale`,
      status: "stale",
      updatedAt: "2020-01-01T00:00:00.000Z",
      updated: "2020-01-01T00:00:00.000Z",
    },
  ];
  return variants[index % variants.length];
}

function withEmailTag(email: string, tag: string) {
  const [local, domain] = email.split("@");
  return domain ? `${local}+${tag}@${domain}` : email;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeScenario(sandboxId: string, scenario?: ScenarioPayload): ScenarioPayload | null {
  if (!scenario || !Array.isArray(scenario.seeds)) return null;
  const profile: Profile =
    scenario.profile === "busy" || scenario.profile === "edge" ? scenario.profile : "baseline";
  return {
    ...scenario,
    sandboxId,
    name: scenario.name?.trim() || `${profileLabel(profile)} scenario`,
    profile,
    generatedAt: scenario.generatedAt || new Date().toISOString(),
    seeds: scenario.seeds.map((seed) => ({
      service: String(seed.service),
      version: String(seed.version),
      resources: Object.fromEntries(
        Object.entries(seed.resources ?? {}).map(([resource, rows]) => [
          resource,
          Array.isArray(rows) ? rows.filter(isRecord) : [],
        ]),
      ),
    })),
  };
}

function rowToScenario(row: ScenarioRow): ScenarioPayload {
  return {
    ...row.seed,
    id: row.id,
    sandboxId: row.sandbox_id,
    name: row.name,
    profile: row.profile,
    generatedAt: row.seed.generatedAt || row.updated_at,
  };
}

function profileLabel(profile: Profile) {
  if (profile === "busy") return "Busy workspace";
  if (profile === "edge") return "Edge case";
  return "Baseline";
}
