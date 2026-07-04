"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Loader2,
  RefreshCw,
  ScanSearch,
  Wrench,
  XCircle,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { RunStatusBadge } from "@/components/run-status-badge";
import {
  fixRun,
  getRun,
  reviewRun,
  type ReviewFinding,
  type ReviewSeverity,
  type Run,
  type TraceStep,
} from "@/lib/sandbox-api";
import { cn } from "@/lib/utils";

const severityStyles: Record<ReviewSeverity, string> = {
  high: "border-red-200 bg-red-50 text-red-900",
  med: "border-amber-200 bg-amber-50 text-amber-900",
  low: "border-slate-200 bg-slate-50 text-slate-800",
};

export function RunDetail({ id }: { id: string }) {
  const router = useRouter();
  const [run, setRun] = React.useState<Run | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [fixing, setFixing] = React.useState(false);
  const [reviewing, setReviewing] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRun(await getRun(id));
    } catch {
      setError("This run could not be found.");
    } finally {
      setLoading(false);
    }
  }, [id]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function review() {
    setReviewing(true);
    try {
      const reviewed = await reviewRun(id);
      setRun(reviewed);
      const n = reviewed.review.findings.length;
      toast.success(n > 0 ? `Judge tagged ${n} step${n === 1 ? "" : "s"}` : "No issues found");
    } catch {
      toast.error("Could not review this trace.");
    } finally {
      setReviewing(false);
    }
  }

  async function fix() {
    if (!run) return;
    setFixing(true);
    try {
      const created = await fixRun(run.id);
      toast.success("Fix started");
      router.push(`/runs/${created.id}`);
    } catch {
      toast.error("Could not start a fix.");
      setFixing(false);
    }
  }

  const findings = React.useMemo(() => run?.review.findings ?? [], [run]);
  // step index -> findings citing it, for inline annotations.
  const byStep = React.useMemo(() => {
    const map = new Map<number, ReviewFinding[]>();
    for (const finding of findings) {
      for (const step of finding.steps) {
        map.set(step, [...(map.get(step) ?? []), finding]);
      }
    }
    return map;
  }, [findings]);

  const verdictIssues = React.useMemo(() => {
    const issues = run?.verdict?.issues;
    return Array.isArray(issues) ? issues.map((issue) => String(issue)) : [];
  }, [run]);

  const canFix = !!run && (run.status === "failed" || run.status === "error" || findings.length > 0);

  return (
    <AppShell>
      <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <Link
          href="/runs"
          className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Runs
        </Link>

        {loading ? (
          <Skeleton className="h-64 w-full rounded-lg" />
        ) : error || !run ? (
          <Card className="rounded-lg border-red-200 bg-red-50 shadow-none">
            <CardContent className="flex min-h-[220px] flex-col items-center justify-center p-8 text-center">
              <AlertCircle className="size-9 text-red-600" />
              <p className="mt-4 text-sm text-red-800">{error ?? "Not found."}</p>
              <Button className="mt-5" variant="outline" onClick={load}>
                <RefreshCw />
                Retry
              </Button>
            </CardContent>
          </Card>
        ) : (
          <>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-2xl font-semibold tracking-normal text-foreground">
                    {run.workflowName ?? "Workflow run"}
                  </h1>
                  <RunStatusBadge status={run.status} />
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {run.fixOf ? "Fix attempt · " : ""}
                  {new Date(run.createdAt).toLocaleString()}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button variant="outline" onClick={review} disabled={reviewing || run.trajectory.length === 0}>
                  {reviewing ? <Loader2 className="animate-spin" /> : <ScanSearch />}
                  {reviewing ? "Reviewing…" : "Review trace"}
                </Button>
                {canFix && (
                  <Button onClick={fix} disabled={fixing}>
                    {fixing ? <Loader2 className="animate-spin" /> : <Wrench />}
                    {fixing ? "Starting…" : "Generate fix"}
                  </Button>
                )}
              </div>
            </div>

            {(verdictIssues.length > 0 || run.error) && (
              <Card className="rounded-lg border-red-200 bg-red-50/60 shadow-none">
                <CardHeader className="border-b border-red-200/70">
                  <CardTitle className="flex items-center gap-2 text-base text-red-950">
                    <XCircle className="size-4 text-red-600" />
                    What went wrong
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-1.5 p-4 text-sm text-red-900">
                  {run.error && <p>{run.error}</p>}
                  {verdictIssues.map((issue, index) => (
                    <p key={index}>• {issue}</p>
                  ))}
                </CardContent>
              </Card>
            )}

            {run.review.reviewedAt && (
              <Card className="rounded-lg shadow-none">
                <CardHeader className="flex flex-row items-center justify-between border-b">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <ScanSearch className="size-4 text-primary" />
                    Judge review
                  </CardTitle>
                  <SeverityCounts findings={findings} />
                </CardHeader>
                <CardContent className="space-y-2 p-4">
                  {run.review.summary && (
                    <p className="text-sm text-muted-foreground">{run.review.summary}</p>
                  )}
                  {findings.map((finding, index) => (
                    <FindingCard key={index} finding={finding} />
                  ))}
                </CardContent>
              </Card>
            )}

            <Card className="rounded-lg shadow-none">
              <CardHeader className="border-b">
                <CardTitle className="text-base">Trace</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {run.trajectory.length > 0 ? (
                  <ol className="divide-y">
                    {run.trajectory.map((step, index) => (
                      <TraceRow
                        key={index}
                        index={index}
                        step={step}
                        findings={byStep.get(index) ?? []}
                      />
                    ))}
                  </ol>
                ) : (
                  <p className="p-6 text-sm text-muted-foreground">
                    No trace yet — this run hasn’t executed.
                  </p>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </AppShell>
  );
}

function SeverityCounts({ findings }: { findings: ReviewFinding[] }) {
  const count = (severity: ReviewSeverity) => findings.filter((f) => f.severity === severity).length;
  const items: [ReviewSeverity, string][] = [
    ["high", "bg-red-100 text-red-700"],
    ["med", "bg-amber-100 text-amber-700"],
    ["low", "bg-slate-100 text-slate-700"],
  ];
  return (
    <div className="flex gap-1.5">
      {items.map(([severity, style]) =>
        count(severity) > 0 ? (
          <Badge key={severity} variant="secondary" className={cn("h-5 rounded-md px-1.5 text-[11px]", style)}>
            {count(severity)} {severity}
          </Badge>
        ) : null,
      )}
    </div>
  );
}

function FindingCard({ finding }: { finding: ReviewFinding }) {
  return (
    <div className={cn("rounded-lg border p-3 text-sm", severityStyles[finding.severity])}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="h-5 rounded-md bg-background/70 px-1.5 text-[11px] capitalize">
          {finding.axis}
        </Badge>
        <span className="font-medium">{finding.title}</span>
        <span className="text-xs opacity-70">
          step{finding.steps.length === 1 ? "" : "s"} {finding.steps.map((s) => s + 1).join(", ")}
        </span>
      </div>
      {finding.recommendation && <p className="mt-1.5 opacity-90">{finding.recommendation}</p>}
    </div>
  );
}

function TraceRow({
  index,
  step,
  findings,
}: {
  index: number;
  step: TraceStep;
  findings: ReviewFinding[];
}) {
  const label = pick(step, ["tool", "action", "name", "type"]) ?? `Step ${index + 1}`;
  const detail = pick(step, ["detail", "output", "message", "content", "input"]);
  const status = pick(step, ["status"]);
  const ok = status !== "error" && status !== "failed";

  return (
    <li className="flex gap-3 p-4">
      <span className="mt-0.5 shrink-0">
        {ok ? (
          <CheckCircle2 className="size-4 text-emerald-600" />
        ) : (
          <XCircle className="size-4 text-red-600" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-muted-foreground">{index + 1}</span>
          <span className="truncate text-sm font-medium text-foreground">{label}</span>
          {status && <span className="text-xs text-muted-foreground">· {String(status)}</span>}
        </div>
        {detail ? (
          <p className="mt-1 break-words text-sm text-muted-foreground">{String(detail)}</p>
        ) : (
          <pre className="mt-1 overflow-x-auto rounded-md bg-muted/60 p-2 text-xs text-muted-foreground">
            {JSON.stringify(step, null, 2)}
          </pre>
        )}
        {/* Inline judge annotations on this step, like code-review comments. */}
        {findings.map((finding, i) => (
          <div
            key={i}
            className={cn("mt-2 rounded-md border px-2.5 py-1.5 text-xs", severityStyles[finding.severity])}
          >
            <span className="font-medium capitalize">{finding.axis}:</span> {finding.title}
            {finding.recommendation && <span className="opacity-90"> — {finding.recommendation}</span>}
          </div>
        ))}
      </div>
    </li>
  );
}

function pick(step: TraceStep, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = step[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return undefined;
}
