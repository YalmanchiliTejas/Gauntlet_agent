import { NextRequest, NextResponse } from "next/server";

import { branchesByRepo } from "@/lib/mock-data";
import { backendFetch } from "@/lib/server/gauntlet-backend";

type BackendBranch = {
  name: string;
  protected?: boolean | null;
  commit_sha?: string | null;
};

export async function GET(request: NextRequest) {
  const repo = request.nextUrl.searchParams.get("repo") || "";
  const installationId = request.nextUrl.searchParams.get("installationId");
  const [owner, name] = repo.split("/");

  if (!owner || !name) {
    return NextResponse.json({ detail: "repo must be in owner/name format." }, { status: 400 });
  }

  try {
    const query = installationId ? `?installation_id=${installationId}` : "";
    const payload = await backendFetch<{ branches: BackendBranch[] }>(
      `/api/github/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/branches${query}`,
      undefined,
      request,
    );
    return NextResponse.json({
      branches: payload.branches.map((branch) => ({
        name: branch.name,
        protected: Boolean(branch.protected),
        sha: branch.commit_sha ?? null,
      })),
      source: "github_app",
    });
  } catch {
    return NextResponse.json({
      branches: branchesByRepo[repo] ?? [{ name: "main", protected: true }],
      source: "mock",
    });
  }
}
