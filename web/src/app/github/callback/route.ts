import { NextRequest, NextResponse } from "next/server";

import { backendFetch, BackendApiError } from "@/lib/server/gauntlet-backend";

export async function GET(request: NextRequest) {
  const installationId = Number(request.nextUrl.searchParams.get("installation_id"));
  const setupAction = request.nextUrl.searchParams.get("setup_action");

  if (!Number.isInteger(installationId) || installationId <= 0) {
    return NextResponse.redirect(new URL("/sandboxes?github_error=missing_installation", request.url));
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
    return NextResponse.redirect(new URL(`/sandboxes?github_error=${reason}`, request.url));
  }
}
