"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ExternalLink,
  ExternalLink,
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
  pollRunStatus,
  reviewRun,
  type ReviewFinding,
  type ReviewSeverity,
  type Run,
  type RunStatus,
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
      const fetched = await getRun(id);
      if (fetched.trajectory.length === 0) {
        try {
          const { run: synced } = await pollRunStatus(id);
          setRun(synced);
          return;
        } catch {
          // Keep the Supabase row if the backend status endpoint is unavailable.
        }
      }
      setRun(fetched);
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

  // Poll for status updates while the run is active (queued or running).
  React.useEffect(() => {
    const TERMINAL: RunStatus[] = ["succeeded", "passed", "failed", "canceled", "error"];
    if (!run || TERMINAL.includes(run.status)) return;

    const interval = window.setInterval(async () => {
      try {
        const { run: updated } = await pollRunStatus(id);
        setRun(updated);
      } catch {
        // Ignore poll errors — next interval will retry.
      }
    }, 4000);

    return () => window.clearInterval(interval);
  }, [id, run]);

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
    if (!Array.isArray(issues)) return [];
    // Judge issues are objects { issue, recommendation, severity, evidence_steps } — pull
    // the human-readable fields instead of String(obj) (which renders "[object Object]").
    return issues.map((raw) => {
      if (typeof raw === "string") return { text: raw, recommendation: "", severity: "" };
      const o = (raw ?? {}) as Record<string, unknown>;
      return {
        text: String(o.issue ?? o.detail ?? o.message ?? JSON.stringify(o)),
        recommendation: typeof o.recommendation === "string" ? o.recommendation : "",
        severity: typeof o.severity === "string" ? o.severity : "",
      };
    });
  }, [run]);

  // A run can succeed yet still have judge findings (optimizations). Only call it an error
  // when the run actually failed or errored.
  const findingsAreErrors = !!run && (run.status === "failed" || run.status === "error" || !!run.error);

  const canFix = !!run && (run.status === "failed" || run.status === "error" || findings.length > 0);
  const isFixRun = !!run?.fixOf;
  const fixPrUrl = typeof run?.verdict?.pr_url === "string" ? run.verdict.pr_url : null;
  const fixNote = typeof run?.verdict?.note === "string" ? run.verdict.note : null;
  const fixDiff = typeof run?.verdict?.diff === "string" ? run.verdict.diff : null;
  const changedFiles = Array.isArray(run?.verdict?.changed_files)
    ? run.verdict.changed_files.filter((file): file is string => typeof file === "string")
    : [];
  const showFixResult = isFixRun && (fixPrUrl || fixNote || fixDiff || changedFiles.length > 0 || run?.status === "succeeded");

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
              <Card className={`rounded-lg shadow-none ${findingsAreErrors ? "border-red-200 bg-red-50/60" : "border-amber-200 bg-amber-50/60"}`}>
                <CardHeader className={`border-b ${findingsAreErrors ? "border-red-200/70" : "border-amber-200/70"}`}>
                  <CardTitle className={`flex items-center gap-2 text-base ${findingsAreErrors ? "text-red-950" : "text-amber-950"}`}>
                    <XCircle className={`size-4 ${findingsAreErrors ? "text-red-600" : "text-amber-600"}`} />
                    {findingsAreErrors ? "What went wrong" : `Judge findings (${verdictIssues.length})`}
                  </CardTitle>
                </CardHeader>
                <CardContent className={`space-y-2.5 p-4 text-sm ${findingsAreErrors ? "text-red-900" : "text-amber-900"}`}>
                  {run.error && <p>{run.error}</p>}
                  {verdictIssues.map((issue, index) => (
                    <div key={index}>
                      <p>• {issue.severity ? `[${issue.severity}] ` : ""}{issue.text}</p>
                      {issue.recommendation && (
                        <p className="ml-3 mt-0.5 text-xs opacity-80">↳ {issue.recommendation}</p>
                      )}
                    </div>
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

            {showFixResult && (
              <Card className="rounded-lg border-emerald-200 bg-emerald-50/60 shadow-none">
                <CardHeader className="border-b border-emerald-200/70">
                  <CardTitle className="flex items-center gap-2 text-base text-emerald-950">
                    <Wrench className="size-4 text-emerald-700" />
                    Fix result
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 p-4 text-sm text-emerald-900">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <p>{fixNote ?? (fixPrUrl ? "The verified fix is ready for review." : "Fix completed, but no PR URL was returned by the backend.")}</p>
                    {fixPrUrl && (
                      <a
                        href={fixPrUrl}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-emerald-300 bg-background px-2.5 text-sm font-medium text-emerald-900 transition-colors hover:bg-emerald-100"
                      >
                        Open PR
                        <ExternalLink className="size-4" />
                      </a>
                    )}
                  </div>
                  {changedFiles.length > 0 && (
                    <div>
                      <p className="text-xs font-medium uppercase tracking-normal text-emerald-800">Changed files</p>
                      <ul className="mt-1 list-inside list-disc space-y-0.5 font-mono text-xs">
                        {changedFiles.map((file) => (
                          <li key={file}>{file}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {fixDiff && (
                    <pre className="max-h-80 overflow-auto rounded-md border border-emerald-200 bg-background p-3 text-xs text-foreground">
                      {fixDiff}
                    </pre>
                  )}
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
                    {isFixRun
                      ? "This fix attempt did not return a workflow execution trace. Fix output appears above when the backend returns it."
                      : "No trace yet — this run hasn’t executed."}
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
