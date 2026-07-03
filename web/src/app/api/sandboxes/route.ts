import { NextRequest, NextResponse } from "next/server";

import { initialSandboxes, twinOptions, type Sandbox } from "@/lib/mock-data";

function humanizeRepoName(repoName: string) {
  const label = repoName.replace(/[-_]+/g, " ").replace(/\bagent\b/i, "agent").trim();
  return label.charAt(0).toUpperCase() + label.slice(1);
}

export async function GET() {
  return NextResponse.json({ sandboxes: initialSandboxes, source: "mock" });
}

export async function POST(request: NextRequest) {
  const body = (await request.json()) as {
    repo?: string;
    branch?: string;
    twinIds?: string[];
  };

  if (!body.repo || !body.branch) {
    return NextResponse.json(
      { detail: "repo and branch are required." },
      { status: 400 },
    );
  }

  const repoName = body.repo.split("/").pop() ?? "agent";
  const twins = (body.twinIds ?? [])
    .map((id) => twinOptions.find((twin) => twin.id === id)?.name)
    .filter((name): name is string => Boolean(name));

  const sandbox: Sandbox = {
    id: `sandbox_${Date.now()}`,
    name: humanizeRepoName(repoName),
    repo: body.repo,
    branch: body.branch,
    status: "Ready",
    twins,
    workflowCount: 0,
    lastRun: "Never run",
  };

  return NextResponse.json({ sandbox, source: "local" }, { status: 201 });
}
