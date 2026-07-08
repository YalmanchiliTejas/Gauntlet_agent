"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import Link from "next/link";

import { signInWithToken } from "@/lib/sandbox-api";
import { getSupabaseClient } from "@/lib/supabase";

type PageState = { status: "loading" } | { status: "error"; message: string };

function getInitialState(): PageState {
  if (typeof window === "undefined") return { status: "loading" };
  if (!getSupabaseClient()) {
    return { status: "error", message: "Supabase is not configured (NEXT_PUBLIC_SUPABASE_URL missing)." };
  }
  const params = new URLSearchParams(window.location.search);
  const errorParam = params.get("error_description");
  if (errorParam) return { status: "error", message: decodeURIComponent(errorParam) };
  return { status: "loading" };
}

export default function AuthCallbackPage() {
  const router = useRouter();
  const [state, setState] = React.useState<PageState>(getInitialState);

  const fail = React.useCallback((msg: string) => {
    setState({ status: "error", message: msg });
  }, []);

  React.useEffect(() => {
    if (state.status === "error") return;

    const supabase = getSupabaseClient();
    if (!supabase) return;

    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");

    async function storeAndRedirect(token: string) {
      try {
        await signInWithToken(token);
        router.replace(`${window.location.origin}/sandboxes`);
      } catch {
        fail("Signed in but could not reach the Gauntlet backend.");
      }
    }

    if (code) {
      // PKCE flow: exchange the one-time code for a session.
      supabase.auth.exchangeCodeForSession(code).then(({ data, error }) => {
        if (error || !data.session?.access_token) {
          fail(error?.message ?? "Could not exchange code for session.");
          return;
        }
        void storeAndRedirect(data.session.access_token);
      });
    } else {
      // Implicit flow fallback: Supabase client reads the hash fragment automatically.
      supabase.auth.getSession().then(({ data }) => {
        const token = data.session?.access_token;
        if (!token) {
          fail("No session found after sign-in.");
          return;
        }
        void storeAndRedirect(token);
      });
    }
  }, [router, fail, state.status]);

  if (state.status === "error") {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm font-medium text-destructive">Sign-in failed</p>
        <p className="max-w-xs text-sm text-muted-foreground">{state.message}</p>
        <Link href="/sandboxes" className="text-sm text-primary underline underline-offset-2">
          Back to Gauntlet
        </Link>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col items-center justify-center gap-3 text-muted-foreground">
      <Loader2 className="size-5 animate-spin" />
      <p className="text-sm">Signing in…</p>
    </div>
  );
}
