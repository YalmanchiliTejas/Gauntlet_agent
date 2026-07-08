import type { RunReview, ReviewFinding, TraceStep } from "@/lib/sandbox-api";

function field(step: TraceStep, keys: string[]): string {
  for (const key of keys) {
    const value = step[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
}

// Heuristic trace reviewer: reads the agent's steps and tags inefficiencies /
// likely fixes, code-reviewer style. Defers to a real judge (GAUNTLET_JUDGE_URL)
// when configured; otherwise applies the rules below. Mirrors the judge's
// finding shape (axis / severity / evidence steps / recommendation).
export async function reviewTrace(trajectory: TraceStep[]): Promise<RunReview> {
  const base = process.env.GAUNTLET_JUDGE_URL?.replace(/\/$/, "");
  if (base) {
    try {
      const res = await fetch(`${base}/review`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": process.env.GAUNTLET_API_KEY ?? "",
        },
        body: JSON.stringify({ trajectory }),
        cache: "no-store",
      });
      if (res.ok) {
        const data = (await res.json()) as Partial<RunReview>;
        if (Array.isArray(data.findings)) {
          return { summary: data.summary, findings: data.findings, reviewedAt: new Date().toISOString() };
        }
      }
    } catch {
      // fall through to the heuristic
    }
  }
  return heuristicReview(trajectory);
}

function heuristicReview(trajectory: TraceStep[]): RunReview {
  const findings: ReviewFinding[] = [];
  const seen = new Map<string, number>(); // tool+detail signature -> first step index

  trajectory.forEach((step, index) => {
    const tool = field(step, ["tool", "action", "name", "type"]) || `step ${index + 1}`;
    const status = field(step, ["status"]);
    const detail = field(step, ["detail", "output", "message", "content", "input"]);

    // 1. Failed / errored step — a correctness problem to fix.
    if (status === "error" || status === "failed") {
      findings.push({
        steps: [index],
        axis: "correctness",
        severity: "high",
        title: `${tool} failed`,
        recommendation: detail
          ? `Handle this failure: ${detail}`
          : "Add error handling / retry so the agent recovers instead of stopping.",
      });
    }

    // 2. Redundant repeat of an identical call — an efficiency problem.
    const signature = `${tool}::${detail}`.toLowerCase();
    if (detail && seen.has(signature)) {
      findings.push({
        steps: [seen.get(signature)!, index],
        axis: "efficiency",
        severity: "med",
        title: `Redundant ${tool} call`,
        recommendation: "Reuse the earlier result instead of calling the same tool with the same input again.",
      });
    } else if (detail) {
      seen.set(signature, index);
    }
  });

  // 3. Consecutive calls to the same tool — possible batching / looping waste.
  for (let i = 1; i < trajectory.length; i++) {
    const prev = field(trajectory[i - 1], ["tool", "action", "name"]);
    const curr = field(trajectory[i], ["tool", "action", "name"]);
    if (prev && prev === curr) {
      findings.push({
        steps: [i - 1, i],
        axis: "efficiency",
        severity: "low",
        title: `Consecutive ${curr} calls`,
        recommendation: "Consider batching these into one call or paginating deliberately.",
      });
    }
  }

  const bySeverity = (s: ReviewFinding["severity"]) => findings.filter((f) => f.severity === s).length;
  const summary =
    findings.length === 0
      ? "No inefficiencies or issues found in this trace."
      : `${findings.length} finding${findings.length === 1 ? "" : "s"}: ` +
        `${bySeverity("high")} high, ${bySeverity("med")} medium, ${bySeverity("low")} low.`;

  return { summary, findings, reviewedAt: new Date().toISOString() };
}
