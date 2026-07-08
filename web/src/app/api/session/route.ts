import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

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

function isDevBypass(): boolean {
  return process.env.GAUNTLET_DEV_BYPASS === "true" && process.env.NODE_ENV !== "production";
}

function base64UrlJson(value: unknown): string {
  return Buffer.from(JSON.stringify(value))
    .toString("base64url");
}

function createDevAccessToken(): string {
  const now = Math.floor(Date.now() / 1000);
  return [
    base64UrlJson({ alg: "none", typ: "JWT" }),
    base64UrlJson({
      aud: "authenticated",
      exp: now + 60 * 60 * 24,
      iat: now,
      iss: "gauntlet-dev-bypass",
      role: "authenticated",
      sub: "00000000-0000-4000-8000-000000000000",
      email: "dev@gauntlet.local",
    }),
    "dev-signature",
  ].join(".");
}

export async function POST(request: NextRequest) {
  const body = (await request.json().catch(() => ({}))) as SessionRequest;
  const apiUrl = (body.apiUrl || process.env.GAUNTLET_API_URL || DEFAULT_GAUNTLET_API_URL).replace(
    /\/$/,
    "",
  );
  const devBypass = isDevBypass();
  const accessToken = body.accessToken?.trim() || (devBypass ? createDevAccessToken() : "");

  if (!accessToken) {
    return NextResponse.json({ detail: "accessToken is required." }, { status: 400 });
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!devBypass) {
    if (supabaseUrl && supabaseAnon) {
      // Supabase-native verification: the stored token must be a valid Supabase
      // session JWT (which is also what the RLS-scoped write endpoints need).
      const supabase = createClient(supabaseUrl, supabaseAnon, { auth: { persistSession: false } });
      const { data, error } = await supabase.auth.getUser(accessToken);
      if (error || !data.user) {
        return NextResponse.json(
          { detail: error?.message ?? "Invalid Supabase session — sign in again." },
          { status: 401 },
        );
      }
    } else {
      // No Supabase configured: fall back to product-backend verification.
      try {
        await backendFetch(
          "/api/me",
          { headers: { Authorization: `Bearer ${accessToken}` } },
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
