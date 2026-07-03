import { NextRequest, NextResponse } from "next/server";

import { backendFetch } from "@/lib/server/gauntlet-backend";

export async function GET(request: NextRequest) {
  try {
    const me = await backendFetch<{ authenticated?: boolean; user_id?: string; user_email?: string | null }>(
      "/api/me",
      undefined,
      request,
    );
    return NextResponse.json({
      authenticated: Boolean(me.authenticated),
      userId: me.user_id ?? null,
      userEmail: me.user_email ?? null,
    });
  } catch {
    return NextResponse.json({
      authenticated: false,
      userId: null,
      userEmail: null,
    });
  }
}
