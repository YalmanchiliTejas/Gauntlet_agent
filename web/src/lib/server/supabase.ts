import { cookies } from "next/headers";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";

import { API_TOKEN_COOKIE } from "@/lib/server/gauntlet-backend";

// Supabase client scoped to the signed-in user: the request carries their JWT
// so RLS (auth.uid()) applies. Returns null when Supabase isn't configured or
// nobody is signed in — callers fall back to mock data so dev keeps working.
// Explicit opt-in for the no-auth stub (dev only). Real Supabase session JWTs
// still use RLS-backed persistence; only the generated dev token falls through
// to the temporary in-memory/mock behavior.
export function isDevBypass(): boolean {
  return process.env.GAUNTLET_DEV_BYPASS === "true" && process.env.NODE_ENV !== "production";
}

// A JWT is three non-empty dot-separated segments.
function isJwt(token: string): boolean {
  const parts = token.split(".");
  return parts.length === 3 && parts.every((part) => part.length > 0);
}

function isDevAccessToken(token: string): boolean {
  const parts = token.split(".");
  return parts.length === 3 && parts[2] === "dev-signature";
}

export async function getServerSupabase(): Promise<SupabaseClient | null> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anon) return null;

  const token = (await cookies()).get(API_TOKEN_COOKIE)?.value;
  // Must be a Supabase-issued JWT (header.payload.signature). A non-JWT here
  // (e.g. a product-backend API token) makes Supabase reply "Expected 3 parts
  // in JWT" — treat it as unauthenticated so callers return a clean 401 instead.
  if (!token || !isJwt(token)) return null;
  if (isDevBypass() && isDevAccessToken(token)) return null;

  return createClient(url, anon, {
    global: { headers: { Authorization: `Bearer ${token}` } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
