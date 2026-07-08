import crypto from "node:crypto";

import type { DraftRow } from "@/lib/server/generate";
import type { WorkflowRow } from "@/lib/server/workflow-map";

type ComparableWorkflow = {
  name?: string | null;
  description?: string | null;
  task_prompt?: string | null;
  draft?: Record<string, unknown> | null;
};

type ComparableWorkflowItem = {
  id?: string;
  workflow: ComparableWorkflow;
};

export type SkippedWorkflow = {
  name: string;
  matchedWorkflowId?: string;
  matchedWorkflowName?: string;
  reason: string;
};

function normalizeText(value: unknown): string {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9\s:/._-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function serviceNames(draft: Record<string, unknown> | null | undefined): string[] {
  const raw = Array.isArray(draft?.services) ? draft.services : [];
  return raw
    .map((service) => {
      if (typeof service === "string") return service;
      if (service && typeof service === "object" && "name" in service) {
        return String((service as { name?: unknown }).name ?? "");
      }
      return "";
    })
    .map(normalizeText)
    .filter(Boolean)
    .sort();
}

function stringList(draft: Record<string, unknown> | null | undefined, key: string): string[] {
  const raw = draft?.[key];
  return (Array.isArray(raw) ? raw : [])
    .map(normalizeText)
    .filter(Boolean)
    .sort();
}

export function workflowFingerprint(workflow: ComparableWorkflow): string {
  const draft = workflow.draft ?? {};
  const payload = {
    prompt: normalizeText(workflow.task_prompt),
    surface: normalizeText(draft.surface_area),
    services: serviceNames(draft),
    interfaces: stringList(draft, "target_interfaces"),
    capabilities: stringList(draft, "product_capabilities"),
    success: stringList(draft, "success_conditions").slice(0, 6),
  };
  return crypto.createHash("sha256").update(JSON.stringify(payload)).digest("hex");
}

function tokenSet(...values: Array<unknown>): Set<string> {
  const stop = new Set(["the", "and", "for", "with", "from", "that", "this", "into", "using"]);
  const text = normalizeText(values.filter(Boolean).join(" "));
  return new Set(text.split(" ").filter((token) => token.length > 2 && !stop.has(token)));
}

function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let intersection = 0;
  for (const token of a) {
    if (b.has(token)) intersection += 1;
  }
  return intersection / (a.size + b.size - intersection);
}

function serviceOverlap(a: ComparableWorkflow, b: ComparableWorkflow): boolean {
  const aServices = serviceNames(a.draft);
  const bServices = serviceNames(b.draft);
  if (aServices.length === 0 && bServices.length === 0) return true;
  return aServices.some((service) => bServices.includes(service));
}

function surfaceMatches(a: ComparableWorkflow, b: ComparableWorkflow): boolean {
  const aSurface = normalizeText(a.draft?.surface_area);
  const bSurface = normalizeText(b.draft?.surface_area);
  return Boolean(aSurface && bSurface && aSurface === bSurface);
}

export function filterNovelDrafts(
  drafts: DraftRow[],
  existingRows: WorkflowRow[],
): { accepted: DraftRow[]; skipped: SkippedWorkflow[] } {
  const accepted: DraftRow[] = [];
  const skipped: SkippedWorkflow[] = [];
  const existing = existingRows.map((row) => ({
    id: row.id,
    workflow: {
      name: (Array.isArray(row.workflows) ? row.workflows[0] : row.workflows)?.name ?? row.name,
      description:
        (Array.isArray(row.workflows) ? row.workflows[0] : row.workflows)?.description ?? row.description,
      task_prompt:
        (Array.isArray(row.workflows) ? row.workflows[0] : row.workflows)?.task_prompt ?? row.task_prompt,
      draft: ((Array.isArray(row.workflows) ? row.workflows[0] : row.workflows)?.draft ?? row.draft ?? {}) as Record<string, unknown>,
    },
  }));
  const comparable: ComparableWorkflowItem[] = [...existing];

  const seenFingerprints = new Map<string, { id?: string; name?: string }>();
  for (const item of existing) {
    seenFingerprints.set(workflowFingerprint(item.workflow), {
      id: item.id,
      name: item.workflow.name ?? undefined,
    });
  }

  for (const draft of drafts) {
    const fingerprint = workflowFingerprint(draft);
    const exact = seenFingerprints.get(fingerprint);
    if (exact) {
      skipped.push({
        name: draft.name,
        matchedWorkflowId: exact.id,
        matchedWorkflowName: exact.name,
        reason: "Exact workflow fingerprint already exists in this sandbox.",
      });
      continue;
    }

    const candidateTokens = tokenSet(draft.name, draft.description, draft.task_prompt);
    const nearMatch = comparable.find((item) => {
      const existingTokens = tokenSet(
        item.workflow.name,
        item.workflow.description,
        item.workflow.task_prompt,
      );
      return (
        jaccard(candidateTokens, existingTokens) >= 0.72 &&
        serviceOverlap(draft, item.workflow) &&
        (surfaceMatches(draft, item.workflow) || candidateTokens.size < 24)
      );
    });
    if (nearMatch) {
      skipped.push({
        name: draft.name,
        matchedWorkflowId: nearMatch.id,
        matchedWorkflowName: nearMatch.workflow.name ?? undefined,
        reason: "Near-duplicate task, service, and product surface already exists in this sandbox.",
      });
      continue;
    }

    const enriched = {
      ...draft,
      draft: {
        ...draft.draft,
        fingerprint,
        novelty_reason:
          typeof draft.draft.novelty_reason === "string"
            ? draft.draft.novelty_reason
            : "Adds coverage not already assigned to this sandbox.",
      },
    };
    accepted.push(enriched);
    seenFingerprints.set(fingerprint, { name: draft.name });
    comparable.push({
      workflow: enriched,
    });
  }

  return { accepted, skipped };
}
