"use client";

import * as React from "react";
import Link from "next/link";
import { AlertCircle, ArrowUpRight, ExternalLink, RefreshCw, Wrench } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { RunStatusBadge } from "@/components/run-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { listRuns, type Run } from "@/lib/sandbox-api";

export function FixesWorkspace() {
  const [runs, setRuns] = React.useState<Run[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      setRuns(await listRuns());
    } catch {
      setError("Could not load fixes.");
    }
  }, []);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const fixes = (runs ?? []).filter((run) => run.fixOf);
  const loading = runs === null && !error;

  return (
    <AppShell>
      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal text-foreground">Fixes</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Follow-up runs generated from failed traces or judge findings.
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
          <div className="grid gap-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-16 w-full rounded-lg" />
            ))}
          </div>
        ) : fixes.length > 0 ? (
          <Card className="rounded-lg shadow-none">
            <CardContent className="divide-y p-0">
              {fixes.map((run) => (
                <div
                  key={run.id}
                  className="grid gap-3 p-4 transition-colors hover:bg-muted/60 sm:grid-cols-[1fr_120px_160px_36px] sm:items-center"
                >
                  <div className="min-w-0">
                    <Link href={`/runs/${run.id}`} className="truncate text-sm font-medium text-foreground hover:underline">
                      {run.workflowName ?? "Fix run"}
                    </Link>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Fix of {run.fixOf} · {run.trajectory.length} step
                      {run.trajectory.length === 1 ? "" : "s"}
                    </div>
                  </div>
                  <RunStatusBadge status={run.status} />
                  <div className="text-sm text-muted-foreground">
                    {new Date(run.createdAt).toLocaleString()}
                  </div>
                  <FixRunAction run={run} />
                </div>
              ))}
            </CardContent>
          </Card>
        ) : (
          <Card className="rounded-lg border-dashed shadow-none">
            <CardContent className="flex min-h-[300px] flex-col items-center justify-center p-8 text-center">
              <div className="flex size-11 items-center justify-center rounded-lg bg-accent text-primary">
                <Wrench className="size-5" />
              </div>
              <h2 className="mt-4 text-lg font-semibold">No fixes yet</h2>
              <p className="mt-2 max-w-sm text-sm text-muted-foreground">
                Generate a fix from a failed run or a reviewed trace to see it here.
              </p>
            </CardContent>
          </Card>
        )}
      </main>
    </AppShell>
  );
}

function FixRunAction({ run }: { run: Run }) {
  const prUrl = typeof run.verdict.pr_url === "string" ? run.verdict.pr_url : null;
  if (prUrl) {
    return (
      <a
        href={prUrl}
        target="_blank"
        rel="noreferrer"
        className="inline-flex size-7 items-center justify-center justify-self-end rounded-md text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
        aria-label="Open fix PR"
      >
        <ExternalLink className="size-4" />
      </a>
    );
  }
  return (
    <Link
      href={`/runs/${run.id}`}
      className="hidden size-7 items-center justify-center justify-self-end rounded-md text-muted-foreground transition-colors hover:bg-background hover:text-foreground sm:inline-flex"
      aria-label="Open fix run"
    >
      <ArrowUpRight className="size-4" />
    </Link>
  );
}
