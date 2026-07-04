"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  Boxes,
  CheckCircle2,
  Clock3,
  GitBranch,
  GitFork,
  MoreHorizontal,
  RefreshCw,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { CreateSandboxSheet } from "@/components/create-sandbox-sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { listSandboxes, type SandboxOptionData } from "@/lib/sandbox-api";
import { twinIconMap, type Sandbox, type SandboxStatus } from "@/lib/mock-data";
import { useSandboxStore } from "@/components/sandbox-store";
import { cn } from "@/lib/utils";

export function SandboxesWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  // List lives in the store so it (and any created sandboxes) survives tab
  // navigation. null until first seeded this session.
  const { sandboxes, setSandboxes } = useSandboxStore();
  const [loading, setLoading] = React.useState(sandboxes === null);
  const [error, setError] = React.useState<string | null>(null);
  const [optionData, setOptionData] = React.useState<SandboxOptionData | null>(null);
  const [checkingAuth, setCheckingAuth] = React.useState(true);

  React.useEffect(() => {
    let alive = true;
    fetch("/api/session/state", { cache: "no-store" })
      .then((response) => response.json())
      .then((payload) => {
        if (!alive) return;
        if (!payload.authenticated) {
          router.replace("/login");
          return;
        }
        setCheckingAuth(false);
      })
      .catch(() => {
        if (alive) router.replace("/login");
      });
    return () => {
      alive = false;
    };
  }, [router]);

  // Handle GitHub App install callback results.
  React.useEffect(() => {
    const github = searchParams.get("github");
    const githubError = searchParams.get("github_error");
    if (!github && !githubError) return;

    if (github === "connected") {
      toast.success("GitHub connected", {
        description: "Your repositories are now available. Open Create sandbox to get started.",
      });
    } else if (githubError === "not_authenticated") {
      toast.error("Not signed in", {
        description: "Configure GAUNTLET_API_TOKEN before connecting GitHub.",
      });
    } else if (githubError === "missing_installation") {
      toast.error("GitHub connection failed", {
        description: "No installation ID was returned by GitHub.",
      });
    } else if (githubError) {
      toast.error("GitHub connection failed", {
        description: "Could not link the GitHub App installation. Try again.",
      });
    }

    // Clean the URL.
    router.replace("/sandboxes");
  }, [searchParams, router]);

  const loadSandboxes = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSandboxes(await listSandboxes());
    } catch {
      setError("Could not load sandboxes.");
    } finally {
      setLoading(false);
    }
  }, [setSandboxes]);

  React.useEffect(() => {
    // Already seeded on an earlier tab visit — keep the store's list as-is.
    if (sandboxes !== null) {
      const timer = window.setTimeout(() => {
        setLoading(false);
      }, 0);
      return () => window.clearTimeout(timer);
    }
    const timer = window.setTimeout(() => {
      void loadSandboxes();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [sandboxes, loadSandboxes]);

  function addSandbox(sandbox: Sandbox) {
    setSandboxes((current) => [sandbox, ...(current ?? [])]);
  }

  const items = sandboxes ?? [];
  const stats = [
    { label: "Sandboxes", value: items.length, icon: Boxes },
    {
      label: "Ready",
      value: items.filter((sandbox) => sandbox.status === "Ready").length,
      icon: CheckCircle2,
    },
    {
      label: "Running",
      value: items.filter((sandbox) => sandbox.status === "Running").length,
      icon: Activity,
    },
  ];

  return (
    <AppShell>
      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        {checkingAuth ? (
          <SandboxListSkeleton />
        ) : (
          <>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal text-foreground">
              Sandboxes
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Create isolated agent environments from a repo, branch, and selected twins.
            </p>
          </div>
          <CreateSandboxSheet
            optionData={optionData}
            onOptionsLoaded={setOptionData}
            onCreate={addSandbox}
          />
        </div>


        <div className="grid gap-3 sm:grid-cols-3">
          {loading
            ? Array.from({ length: 3 }).map((_, index) => <StatSkeleton key={index} />)
            : stats.map((stat) => {
                const Icon = stat.icon;
                return (
                  <Card key={stat.label} className="rounded-lg shadow-none">
                    <CardContent className="flex items-center justify-between p-4">
                      <div>
                        <div className="text-sm text-muted-foreground">{stat.label}</div>
                        <div className="mt-1 text-2xl font-semibold">{stat.value}</div>
                      </div>
                      <div className="flex size-9 items-center justify-center rounded-lg bg-accent text-primary">
                        <Icon className="size-4" />
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
        </div>

        {error ? (
          <ErrorState message={error} onRetry={loadSandboxes} />
        ) : loading ? (
          <SandboxListSkeleton />
        ) : items.length > 0 ? (
          <SandboxList sandboxes={items} />
        ) : (
          <EmptySandboxes
            optionData={optionData}
            onOptionsLoaded={setOptionData}
            onCreate={addSandbox}
          />
        )}
          </>
        )}
      </main>
    </AppShell>
  );
}

function SandboxList({ sandboxes }: { sandboxes: Sandbox[] }) {
  return (
    <Card className="rounded-lg shadow-none">
      <CardHeader className="flex flex-col gap-3 border-b sm:flex-row sm:items-center sm:justify-between">
        <div>
          <CardTitle className="text-base">Active sandboxes</CardTitle>
          <CardDescription>Created environments for workflow generation and agent runs.</CardDescription>
        </div>
        <Button variant="outline" size="sm">
          <Clock3 />
          Recent activity
        </Button>
      </CardHeader>
      <CardContent className="p-0">
        <div className="divide-y">
          {sandboxes.map((sandbox) => (
            <Link
              key={sandbox.id}
              href={`/sandboxes/${sandbox.id}`}
              className="grid gap-4 p-4 transition-colors hover:bg-muted/60 lg:grid-cols-[minmax(280px,1fr)_160px_220px_150px_36px] lg:items-center"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="truncate text-sm font-medium text-foreground">
                    {sandbox.name}
                  </div>
                  <StatusBadge status={sandbox.status} />
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5">
                    <GitFork className="size-3.5" />
                    {sandbox.repo}
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <GitBranch className="size-3.5" />
                    {sandbox.branch}
                  </span>
                </div>
              </div>

              <div className="text-sm">
                <div className="font-medium">{sandbox.workflowCount}</div>
                <div className="text-muted-foreground">workflows</div>
              </div>

              <TwinStack twins={sandbox.twins} />

              <div className="text-sm">
                <div className="font-medium">{sandbox.lastRun}</div>
                <div className="text-muted-foreground">last run</div>
              </div>

              <span className="hidden size-7 items-center justify-center justify-self-end rounded-md text-muted-foreground lg:inline-flex">
                <ArrowUpRight className="size-4" />
              </span>
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function EmptySandboxes({
  optionData,
  onOptionsLoaded,
  onCreate,
}: {
  optionData: SandboxOptionData | null;
  onOptionsLoaded: (data: SandboxOptionData) => void;
  onCreate: (sandbox: Sandbox) => void;
}) {
  return (
    <Card className="rounded-lg border-dashed shadow-none">
      <CardContent className="flex min-h-[360px] flex-col items-center justify-center p-8 text-center">
        <div className="flex size-11 items-center justify-center rounded-lg bg-accent text-primary">
          <Boxes className="size-5" />
        </div>
        <h2 className="mt-4 text-lg font-semibold">Create your first sandbox</h2>
        <p className="mt-2 max-w-sm text-sm text-muted-foreground">
          Connect a GitHub repo, choose a branch, and select the twins your agent should use.
        </p>
        <div className="mt-5">
          <CreateSandboxSheet
            optionData={optionData}
            onOptionsLoaded={onOptionsLoaded}
            onCreate={onCreate}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className="rounded-lg border-red-200 bg-red-50 shadow-none">
      <CardContent className="flex min-h-[260px] flex-col items-center justify-center p-8 text-center">
        <AlertCircle className="size-9 text-red-600" />
        <h2 className="mt-4 text-lg font-semibold text-red-950">Sandboxes unavailable</h2>
        <p className="mt-2 text-sm text-red-800">{message}</p>
        <Button className="mt-5" variant="outline" onClick={onRetry}>
          <RefreshCw />
          Retry
        </Button>
      </CardContent>
    </Card>
  );
}

function StatSkeleton() {
  return (
    <Card className="rounded-lg shadow-none">
      <CardContent className="flex items-center justify-between p-4">
        <div>
          <Skeleton className="h-4 w-20" />
          <Skeleton className="mt-3 h-7 w-10" />
        </div>
        <Skeleton className="size-9 rounded-lg" />
      </CardContent>
    </Card>
  );
}

function SandboxListSkeleton() {
  return (
    <Card className="rounded-lg shadow-none">
      <CardHeader className="border-b">
        <Skeleton className="h-5 w-36" />
        <Skeleton className="h-4 w-64" />
      </CardHeader>
      <CardContent className="space-y-0 p-0">
        {Array.from({ length: 3 }).map((_, index) => (
          <div key={index} className="grid gap-4 border-b p-4 lg:grid-cols-[minmax(280px,1fr)_160px_220px_150px]">
            <div>
              <Skeleton className="h-5 w-48" />
              <Skeleton className="mt-3 h-4 w-64" />
            </div>
            <Skeleton className="h-10 w-20" />
            <Skeleton className="h-8 w-44" />
            <Skeleton className="h-10 w-24" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function StatusBadge({ status }: { status: SandboxStatus }) {
  return (
    <Badge
      variant="secondary"
      className={cn(
        "h-5 rounded-md px-1.5 text-[11px] font-medium",
        status === "Ready" && "bg-emerald-50 text-emerald-700",
        status === "Running" && "bg-blue-50 text-blue-700",
        status === "Needs attention" && "bg-amber-50 text-amber-700",
      )}
    >
      {status}
    </Badge>
  );
}

function TwinStack({ twins }: { twins: string[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {twins.map((twin) => {
        const Icon = twinIconMap[twin as keyof typeof twinIconMap] ?? twinIconMap.default;
        return (
          <Badge
            key={twin}
            variant="outline"
            className="h-7 gap-1.5 rounded-md bg-background px-2 font-normal"
          >
            <Icon className="size-3.5 text-muted-foreground" />
            {twin}
          </Badge>
        );
      })}
      {twins.length === 0 && (
        <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
          <MoreHorizontal className="size-4" />
          No twins
        </span>
      )}
    </div>
  );
}
