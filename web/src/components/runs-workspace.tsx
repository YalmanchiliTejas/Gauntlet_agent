"use client";

import * as React from "react";
import Link from "next/link";
import { AlertCircle, ArrowUpRight, PlayCircle, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { listRuns, type Run } from "@/lib/sandbox-api";
import { RunStatusBadge } from "@/components/run-status-badge";

export function RunsWorkspace() {
  const [runs, setRuns] = React.useState<Run[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      setRuns(await listRuns());
    } catch {
      setError("Could not load runs.");
    }
  }, []);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const loading = runs === null && !error;

  return (
    <AppShell>
      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal text-foreground">Runs</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Executions of your workflows against the sandbox twins, with traces and verdicts.
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
        ) : runs && runs.length > 0 ? (
          <Card className="rounded-lg shadow-none">
            <CardContent className="divide-y p-0">
              {runs.map((run) => (
                <Link
                  key={run.id}
                  href={`/runs/${run.id}`}
                  className="grid gap-3 p-4 transition-colors hover:bg-muted/60 sm:grid-cols-[1fr_120px_140px_36px] sm:items-center"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-foreground">
                      {run.workflowName ?? "Workflow run"}
                      {run.fixOf && (
                        <span className="ml-2 text-xs font-normal text-muted-foreground">fix attempt</span>
                      )}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      {run.trajectory.length} step{run.trajectory.length === 1 ? "" : "s"}
                    </div>
                  </div>
                  <RunStatusBadge status={run.status} />
                  <div className="text-sm text-muted-foreground">
                    {new Date(run.createdAt).toLocaleString()}
                  </div>
                  <span className="hidden size-7 items-center justify-center justify-self-end rounded-md text-muted-foreground sm:inline-flex">
                    <ArrowUpRight className="size-4" />
                  </span>
                </Link>
              ))}
            </CardContent>
          </Card>
        ) : (
          <Card className="rounded-lg border-dashed shadow-none">
            <CardContent className="flex min-h-[300px] flex-col items-center justify-center p-8 text-center">
              <div className="flex size-11 items-center justify-center rounded-lg bg-accent text-primary">
                <PlayCircle className="size-5" />
              </div>
              <h2 className="mt-4 text-lg font-semibold">No runs yet</h2>
              <p className="mt-2 max-w-sm text-sm text-muted-foreground">
                Run a workflow from the Workflows tab to see its trace here.
              </p>
            </CardContent>
          </Card>
        )}
      </main>
    </AppShell>
  );
}
