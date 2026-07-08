"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  AlertCircle,
  Boxes,
  CheckCircle2,
  Database,
  GitFork,
  KeyRound,
  Loader2,
  LogOut,
  Mail,
  RefreshCw,
  Unplug,
  User,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  disconnectGitHubInstallation,
  listSandboxOptions,
  listSandboxes,
  signOut,
  type SandboxOptionData,
} from "@/lib/sandbox-api";

type SessionState = {
  authenticated?: boolean;
  userId?: string | null;
  userEmail?: string | null;
};

export function SettingsWorkspace() {
  const [options, setOptions] = React.useState<SandboxOptionData | null>(null);
  const [session, setSession] = React.useState<SessionState | null>(null);
  const [sandboxCount, setSandboxCount] = React.useState(0);
  const [loading, setLoading] = React.useState(true);
  const [disconnecting, setDisconnecting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [optionPayload, sessionPayload, sandboxes] = await Promise.all([
        listSandboxOptions(),
        fetch("/api/session/state", { cache: "no-store" }).then((response) => response.json()),
        listSandboxes().catch(() => []),
      ]);
      setOptions(optionPayload);
      setSession(sessionPayload);
      setSandboxCount(sandboxes.length);
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

  const clearSession = React.useCallback(async () => {
    await signOut();
    window.location.assign("/login");
  }, []);

  async function disconnectGitHub() {
    const installationId = options?.connection.installationId;
    if (!installationId) {
      return;
    }

    setDisconnecting(true);
    setError(null);
    try {
      await disconnectGitHubInstallation(installationId);
      toast.success("GitHub disconnected", {
        description: "The GitHub App was uninstalled from GitHub and unlinked from Gauntlet.",
      });
      await load();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not disconnect GitHub.";
      setError(message);
      toast.error("Could not disconnect GitHub", { description: message });
    } finally {
      setDisconnecting(false);
    }
  }

  return (
    <AppShell>
      <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal text-foreground">Settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage your account, connected repositories, and sandbox defaults.
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
            <Card className="rounded-lg shadow-none">
              <CardHeader className="border-b">
                <CardTitle className="flex items-center gap-2 text-base">
                  <User className="size-4 text-primary" />
                  Account
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 p-4 md:grid-cols-[1fr_auto] md:items-center">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <Mail className="size-4 text-muted-foreground" />
                    {session?.userEmail ?? "No email available"}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <Badge
                      variant="secondary"
                      className="h-5 rounded-md bg-emerald-50 px-1.5 text-[11px] text-emerald-700"
                    >
                      {session?.authenticated ? "Signed in" : "Signed out"}
                    </Badge>
                    {session?.userId && (
                      <span className="text-xs text-muted-foreground">User ID {session.userId}</span>
                    )}
                  </div>
                </div>
                <Button variant="outline" onClick={() => void clearSession()}>
                  <LogOut />
                  Sign out
                </Button>
              </CardContent>
            </Card>

            <div className="grid gap-3 md:grid-cols-3">
              <StatusCard
                title="GitHub"
                icon={GitFork}
                ok={!!options?.connection.connected}
                label={options?.connection.connected ? "Connected" : "Not connected"}
                detail={options?.connection.message ?? "Load settings to inspect GitHub status."}
                action={
                  options?.connection.connected && options.connection.installationId ? (
                    <Button
                      type="button"
                      variant="destructive"
                      size="sm"
                      onClick={() => void disconnectGitHub()}
                      disabled={disconnecting}
                    >
                      {disconnecting ? <Loader2 className="size-3.5 animate-spin" /> : <Unplug />}
                      Disconnect
                    </Button>
                  ) : options?.connection.installUrl ? (
                    <Button size="sm" render={<a href={options.connection.installUrl} />}>
                      <GitFork />
                      Connect
                    </Button>
                  ) : undefined
                }
              />
              <StatusCard
                title="Sandboxes"
                icon={Boxes}
                ok={sandboxCount > 0}
                label={`${sandboxCount} active`}
                detail="Environments connected to your repositories."
                action={
                  <Button size="sm" variant="outline" render={<Link href="/sandboxes" />}>
                    Manage
                  </Button>
                }
              />
              <StatusCard
                title="Seed Data"
                icon={Database}
                ok={sandboxCount > 0}
                label="Per sandbox"
                detail="Generate and edit seeded Gmail, Slack, Stripe, and other twin data from each sandbox."
                action={
                  <Button size="sm" variant="outline" render={<Link href="/sandboxes" />}>
                    Open
                  </Button>
                }
              />
            </div>

            <Card className="rounded-lg shadow-none">
              <CardHeader className="border-b">
                <CardTitle className="flex items-center gap-2 text-base">
                  <KeyRound className="size-4 text-primary" />
                  Preferences
                </CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
                <PreferenceRow label="Default scenario profile" value="Baseline seed" />
                <PreferenceRow label="Run state snapshots" value="Enabled when migrations are applied" />
                <PreferenceRow label="Workflow grouping" value="Repository" />
                <PreferenceRow label="Sidebar state" value="Saved in this browser" />
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
  action,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  ok: boolean;
  label: string;
  detail: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="rounded-lg shadow-none">
      <CardContent className="flex min-h-[142px] flex-col justify-between gap-4 p-4">
        <div className="min-w-0">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">{title}</div>
            <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
              <Icon className="size-4" />
            </div>
          </div>
          <div className="mt-2 flex items-center gap-2 text-base font-semibold">
            {ok ? (
              <CheckCircle2 className="size-4 text-emerald-600" />
            ) : (
              <AlertCircle className="size-4 text-amber-600" />
            )}
            <span>{label}</span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
        </div>
        {action && <div>{action}</div>}
      </CardContent>
    </Card>
  );
}

function PreferenceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="text-sm font-medium">{label}</div>
      <div className="mt-1 text-sm text-muted-foreground">{value}</div>
    </div>
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
