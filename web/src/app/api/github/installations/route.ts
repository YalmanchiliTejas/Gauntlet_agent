import { NextRequest, NextResponse } from "next/server";

import { backendFetch, BackendApiError } from "@/lib/server/gauntlet-backend";

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as {
    installationId?: number | string;
    installation_id?: number | string;
  };
  const installationId = Number(body.installationId ?? body.installation_id);

  if (!Number.isInteger(installationId) || installationId <= 0) {
    return NextResponse.json(
      { detail: "A numeric GitHub installation ID is required." },
      { status: 400 },
    );
  }

  if (process.env.GAUNTLET_DEV_BYPASS === "true" && process.env.NODE_ENV !== "production") {
    return NextResponse.json({ ok: true, installation_id: installationId });
  }

  try {
    const payload = await backendFetch(
      "/api/github/installations",
      {
        method: "POST",
        body: JSON.stringify({
          installation_id: installationId,
          setup_action: "manual_link",
        }),
      },
      request,
    );
    return NextResponse.json(payload);
  } catch (error) {
    const status = error instanceof BackendApiError ? error.status : 500;
    const detail = error instanceof Error ? error.message : "Could not link GitHub installation.";
    return NextResponse.json({ detail }, { status });
  }
}

export async function DELETE(request: NextRequest) {
  const installationId = Number(request.nextUrl.searchParams.get("installationId"));

  if (!Number.isInteger(installationId) || installationId <= 0) {
    return NextResponse.json(
      { detail: "A numeric GitHub installation ID is required." },
      { status: 400 },
    );
  }

  if (process.env.GAUNTLET_DEV_BYPASS === "true" && process.env.NODE_ENV !== "production") {
    return NextResponse.json({ ok: true });
  }

  try {
    const payload = await backendFetch(
      `/api/github/installations/${installationId}`,
      { method: "DELETE" },
      request,
    );

    if ((payload as { uninstalled?: unknown }).uninstalled !== true) {
      return NextResponse.json(
        {
          detail:
            "GitHub was unlinked locally, but the GitHub App was not uninstalled. Update the backend and try again.",
        },
        { status: 502 },
      );
    }

    return NextResponse.json(payload);
  } catch (error) {
    const status = error instanceof BackendApiError ? error.status : 500;
    const detail = error instanceof Error ? error.message : "Could not disconnect GitHub.";
    return NextResponse.json({ detail }, { status });
  }
}
