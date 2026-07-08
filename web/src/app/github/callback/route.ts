import { NextRequest, NextResponse } from "next/server";

import { backendFetch, BackendApiError } from "@/lib/server/gauntlet-backend";

function redirectWithGithubError(request: NextRequest, error: string, detail?: string) {
  const url = new URL("/sandboxes", request.url);
  url.searchParams.set("github_error", error);
  if (detail) {
    url.searchParams.set("github_error_detail", detail.slice(0, 300));
  }
  return NextResponse.redirect(url);
}

export async function GET(request: NextRequest) {
  const installationId = Number(request.nextUrl.searchParams.get("installation_id"));
  const setupAction = request.nextUrl.searchParams.get("setup_action");

  if (!Number.isInteger(installationId) || installationId <= 0) {
    return redirectWithGithubError(request, "missing_installation");
  }

  if (process.env.GAUNTLET_DEV_BYPASS === "true" && process.env.NODE_ENV !== "production") {
    return NextResponse.redirect(new URL("/sandboxes?github=connected", request.url));
  }

  try {
    await backendFetch(
      "/api/github/installations",
      {
        method: "POST",
        body: JSON.stringify({
          installation_id: installationId,
          setup_action: setupAction,
        }),
      },
      request,
    );
    return NextResponse.redirect(new URL("/sandboxes?github=connected", request.url));
  } catch (error) {
    const status = error instanceof BackendApiError ? error.status : 500;
    const reason = status === 401 ? "not_authenticated" : "link_failed";
    const detail = error instanceof Error ? error.message : "Could not link GitHub installation.";
    return redirectWithGithubError(request, reason, detail);
  }
}
