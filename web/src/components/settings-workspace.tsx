"use client";

import * as React from "react";
import { AlertCircle, CheckCircle2, GitFork, KeyRound, RefreshCw, Settings, Unplug } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { listSandboxOptions, requiredGithubUiEndpoints, type SandboxOptionData } from "@/lib/sandbox-api";

type SessionState = {
  authenticated?: boolean;
  source?: string;
};

export function SettingsWorkspace() {
  const [options, setOptions] = React.useState<SandboxOptionData | null>(null);
  const [session, setSession] = React.useState<SessionState | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [optionPayload, sessionPayload] = await Promise.all([
        listSandboxOptions(),
        fetch("/api/session/state", { cache: "no-store" }).then((response) => response.json()),
      ]);
      setOptions(optionPayload);
      setSession(sessionPayload);
    } catch {
      setError("Could not load settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <AppShell>
      <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal text-foreground">Settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Connection status, available twins, and backend endpoints used by this UI.
          </p>
        </div>

        {error ? (
          <Card className="rounded-lg border-red-200 bg-red-50 shadow-none">
            <CardContent className="flex min-h-[220px] flex-col items-center justify-center p-8 text-center">
              <AlertCircle className="size-9 text-red-600" />
              <p className="mt-4 text-sm text-red-800">{error}</p>
              <Button className="mt-5" variant="outline" onClick={load}>
                <RefreshCw />
                Retry
              </Button>
            </CardContent>
          </Card>
        ) : loading ? (
          <SettingsSkeleton />
        ) : (
          <>
            <div className="grid gap-3 md:grid-cols-2">
              <StatusCard
                title="Session"
                icon={KeyRound}
                ok={!!session?.authenticated}
                label={session?.authenticated ? "Authenticated" : "Signed out"}
                detail={session?.source ? `Source: ${session.source}` : "Used for Supabase-backed persistence."}
              />
              <StatusCard
                title="GitHub"
                icon={GitFork}
                ok={!!options?.connection.connected}
                label={options?.connection.connected ? "Connected" : "Not connected"}
                detail={options?.connection.message ?? "Load settings to inspect GitHub status."}
              />
            </div>

            <Card className="rounded-lg shadow-none">
              <CardHeader className="border-b">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Settings className="size-4 text-primary" />
                  Available twins
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-2 p-4 sm:grid-cols-2">
                {(options?.twins ?? []).map((twin) => (
                  <div key={twin.id} className="rounded-lg border bg-card p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <span className={`size-2 rounded-full ${twin.tone}`} />
                        {twin.name}
                      </div>
                      <Badge variant="secondary" className="h-5 rounded-md px-1.5 text-[11px]">
                        {twin.versions[twin.versions.length - 1] ?? "none"}
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{twin.description}</p>
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card className="rounded-lg shadow-none">
              <CardHeader className="border-b">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Unplug className="size-4 text-primary" />
                  Required UI endpoints
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-2 p-4 sm:grid-cols-2">
                {requiredGithubUiEndpoints.map((endpoint) => (
                  <code key={endpoint} className="rounded-md border bg-muted px-2 py-1.5 text-xs">
                    {endpoint}
                  </code>
                ))}
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </AppShell>
  );
}

function StatusCard({
  title,
  icon: Icon,
  ok,
  label,
  detail,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  ok: boolean;
  label: string;
  detail: string;
}) {
  return (
    <Card className="rounded-lg shadow-none">
      <CardContent className="flex items-start justify-between gap-4 p-4">
        <div className="min-w-0">
          <div className="text-sm text-muted-foreground">{title}</div>
          <div className="mt-1 flex items-center gap-2 text-base font-semibold">
            {ok ? <CheckCircle2 className="size-4 text-emerald-600" /> : <AlertCircle className="size-4 text-amber-600" />}
            {label}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
        </div>
        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
          <Icon className="size-4" />
        </div>
      </CardContent>
    </Card>
  );
}

function SettingsSkeleton() {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <Skeleton className="h-32 rounded-lg" />
        <Skeleton className="h-32 rounded-lg" />
      </div>
      <Skeleton className="h-64 rounded-lg" />
      <Skeleton className="h-48 rounded-lg" />
    </div>
  );
}
