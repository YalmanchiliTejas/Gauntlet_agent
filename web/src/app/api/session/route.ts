import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import {
  API_TOKEN_COOKIE,
  API_URL_COOKIE,
  backendFetch,
  BackendApiError,
  DEFAULT_GAUNTLET_API_URL,
} from "@/lib/server/gauntlet-backend";

type SessionRequest = {
  apiUrl?: string;
  accessToken?: string;
};

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as SessionRequest;
  const apiUrl = (body.apiUrl || process.env.GAUNTLET_API_URL || DEFAULT_GAUNTLET_API_URL).replace(
    /\/$/,
    "",
  );
  const accessToken = body.accessToken?.trim();

  if (!accessToken) {
    return NextResponse.json({ detail: "accessToken is required." }, { status: 400 });
  }

  const devBypass = process.env.GAUNTLET_DEV_BYPASS === "true" && process.env.NODE_ENV !== "production";
  if (!devBypass) {
    try {
      await backendFetch(
        "/api/me",
        {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        },
        new NextRequest(request.url, {
          headers: {
            authorization: `Bearer ${accessToken}`,
            "x-gauntlet-api-url": apiUrl,
          },
        }),
      );
    } catch (error) {
      const status = error instanceof BackendApiError ? error.status : 500;
      const detail = error instanceof Error ? error.message : "Could not verify credentials.";
      return NextResponse.json({ detail }, { status });
    }
  }

  const store = await cookies();
  const secure = process.env.NODE_ENV === "production";
  const cookieOptions = {
    httpOnly: true,
    secure,
    sameSite: "lax" as const,
    path: "/",
    maxAge: 60 * 60 * 24 * 14,
  };
  store.set(API_URL_COOKIE, apiUrl, cookieOptions);
  store.set(API_TOKEN_COOKIE, accessToken, cookieOptions);

  return NextResponse.json({ ok: true });
}

export async function DELETE() {
  const store = await cookies();
  store.delete(API_URL_COOKIE);
  store.delete(API_TOKEN_COOKIE);
  return NextResponse.json({ ok: true });
}
