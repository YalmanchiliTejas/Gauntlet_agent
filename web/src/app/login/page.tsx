"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getAuthCallbackUrl } from "@/lib/auth-redirect";
import { signInWithToken } from "@/lib/sandbox-api";
import { getSupabaseClient } from "@/lib/supabase";

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
    </svg>
  );
}

function GithubIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M12 0C5.373 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.6.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c.955.004 1.917.129 2.817.376 2.29-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
    </svg>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const supabase = React.useMemo(() => getSupabaseClient(), []);
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [loading, setLoading] = React.useState<"email" | "google" | "github" | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [debugUrl, setDebugUrl] = React.useState<string | null>(null);

  async function finishSignIn(accessToken: string) {
    await signInWithToken(accessToken);
    router.replace("/sandboxes");
    router.refresh();
  }

  async function handleEmailSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLoading("email");
    try {
      if (!supabase) throw new Error("Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.");
      const { data, error: signInError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (signInError) throw signInError;
      const token = data.session?.access_token;
      if (!token) throw new Error("Supabase did not return a session.");
      await finishSignIn(token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed.");
      setLoading(null);
    }
  }

  async function handleOAuth(provider: "google" | "github") {
    setError(null);
    setLoading(provider);
    try {
      if (!supabase) throw new Error("Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.");
      const redirectTo = getAuthCallbackUrl();
      const { data, error: signInError } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo,
          skipBrowserRedirect: true,
          queryParams: provider === "google" ? { prompt: "select_account" } : undefined,
        },
      });
      if (signInError) throw signInError;
      if (!data.url) throw new Error("Supabase did not return an OAuth URL.");
      const url = new URL(data.url);
      url.searchParams.set("redirect_to", redirectTo);
      const nextUrl = url.toString();
      setDebugUrl(nextUrl);
      window.location.assign(nextUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start OAuth sign-in.");
      setLoading(null);
    }
  }

  async function previewOAuth(provider: "google" | "github") {
    setError(null);
    try {
      if (!supabase) throw new Error("Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.");
      const redirectTo = getAuthCallbackUrl();
      const { data, error: signInError } = await supabase.auth.signInWithOAuth({
        provider,
        options: {
          redirectTo,
          skipBrowserRedirect: true,
          queryParams: provider === "google" ? { prompt: "select_account" } : undefined,
        },
      });
      if (signInError) throw signInError;
      if (!data.url) throw new Error("Supabase did not return an OAuth URL.");
      const url = new URL(data.url);
      url.searchParams.set("redirect_to", redirectTo);
      setDebugUrl(url.toString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate OAuth URL.");
    }
  }

  const busy = loading !== null;

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-10 text-foreground">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <ShieldCheck className="size-5" />
          </div>
          <div>
            <h1 className="text-base font-semibold">Sign in to Gauntlet</h1>
            <p className="text-sm text-muted-foreground">Use your workspace account.</p>
          </div>
        </div>

        <div className="space-y-2">
          <Button
            type="button"
            variant="outline"
            className="w-full gap-2"
            disabled={busy}
            onClick={() => void handleOAuth("google")}
          >
            {loading === "google" ? <Loader2 className="size-4 animate-spin" /> : <GoogleIcon className="size-4" />}
            Continue with Google
          </Button>
          <Button
            type="button"
            variant="outline"
            className="w-full gap-2"
            disabled={busy}
            onClick={() => void handleOAuth("github")}
          >
            {loading === "github" ? <Loader2 className="size-4 animate-spin" /> : <GithubIcon className="size-4" />}
            Continue with GitHub
          </Button>
        </div>

        <div className="my-6 flex items-center gap-3 text-xs uppercase tracking-[0.18em] text-muted-foreground">
          <div className="h-px flex-1 bg-border" />
          or
          <div className="h-px flex-1 bg-border" />
        </div>

        <form onSubmit={handleEmailSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              minLength={6}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          <Button type="submit" className="w-full gap-2" disabled={busy}>
            {loading === "email" && <Loader2 className="size-4 animate-spin" />}
            Sign in
          </Button>
        </form>

        {error && <p className="mt-4 text-sm text-destructive">{error}</p>}

        <div className="mt-5 rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
          <div className="font-medium text-foreground">Local auth redirect</div>
          <div className="mt-1 break-all">{getAuthCallbackUrl()}</div>
          <div className="mt-3 flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => void previewOAuth("google")}
            >
              Preview Google URL
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => void previewOAuth("github")}
            >
              Preview GitHub URL
            </Button>
          </div>
          {debugUrl && (
            <>
              <div className="mt-3 font-medium text-foreground">Last OAuth URL</div>
              <div className="mt-1 break-all">{debugUrl}</div>
            </>
          )}
        </div>

        <div className="mt-6 text-center text-sm text-muted-foreground">
          <Link href="/sandboxes" className="underline underline-offset-4">
            Back to sandboxes
          </Link>
        </div>
      </div>
    </main>
  );
}
