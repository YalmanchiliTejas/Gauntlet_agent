import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { createClient } from "@supabase/supabase-js";

import { backendFetch } from "@/lib/server/gauntlet-backend";
import { API_TOKEN_COOKIE } from "@/lib/server/gauntlet-backend";

export async function GET(request: NextRequest) {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  const accessToken = (await cookies()).get(API_TOKEN_COOKIE)?.value;

  if (supabaseUrl && supabaseAnon && accessToken) {
    const supabase = createClient(supabaseUrl, supabaseAnon, { auth: { persistSession: false } });
    const { data } = await supabase.auth.getUser(accessToken);
    if (data.user) {
      return NextResponse.json({
        authenticated: true,
        userId: data.user.id,
        userEmail: data.user.email ?? null,
      });
    }
  }

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
