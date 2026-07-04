import type { DocInput } from "@/lib/sandbox-api";

export type GenerateInput = {
  docs: DocInput[];
  services: { name: string; version?: string | null }[];
  count: number;
  workflowName?: string;
  focus?: string;
  existingWorkflows?: Array<{
    name: string;
    description?: string | null;
    task_prompt?: string | null;
    draft?: Record<string, unknown> | null;
  }>;
};

// A row ready to insert into sandbox_workflows (minus sandbox_id/user_id).
export type DraftRow = {
  name: string;
  description: string | null;
  difficulty: string | null;
  task_prompt: string | null;
  draft: Record<string, unknown>;
};

function firstSentence(text: string): string {
  const trimmed = text.trim();
  const end = trimmed.search(/[.!?](\s|$)/);
  return (end === -1 ? trimmed : trimmed.slice(0, end + 1)).slice(0, 240);
}

type GeneratedDraft = {
  name?: string;
  description?: string;
  difficulty?: string;
  task_prompt?: string;
};

function draftRowFromGenerated(wf: GeneratedDraft): DraftRow {
  return {
    name: wf.name ?? "workflow",
    description: wf.description ?? null,
    difficulty: wf.difficulty ?? null,
    task_prompt: wf.task_prompt ?? null,
    draft: wf as Record<string, unknown>,
  };
}

function applyWorkflowName(rows: DraftRow[], workflowName?: string): DraftRow[] {
  const name = workflowName?.trim();
  if (!name) return rows;
  return rows.map((row, index) => ({
    ...row,
    name: rows.length === 1 ? name : `${name} ${index + 1}`,
    draft: {
      ...row.draft,
      name: rows.length === 1 ? name : `${name} ${index + 1}`,
    },
  }));
}

// Turn docs + services into workflow drafts. Uses the Python generator
// (generate_workflows_json) when GAUNTLET_WORKFLOW_URL is set; otherwise
// derives one draft per doc so the flow still works without the backend.
export async function generateDrafts(input: GenerateInput): Promise<DraftRow[]> {
  const focus = input.focus?.trim();
  const base = process.env.GAUNTLET_WORKFLOW_URL?.replace(/\/$/, "");
  if (base) {
    try {
      const res = await fetch(`${base}/workflows/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": process.env.GAUNTLET_API_KEY ?? "",
        },
        body: JSON.stringify({
          docs: input.docs,
          services: input.services.map((s) => ({
            name: s.name,
            version: s.version ?? undefined,
          })),
          focus,
          existing_workflows: input.existingWorkflows ?? [],
          coverage: { count: input.count },
        }),
        cache: "no-store",
      });
      if (res.ok) {
        const data = (await res.json()) as { workflows?: GeneratedDraft[] };
        const workflows = data.workflows ?? [];
        if (workflows.length > 0) {
          return applyWorkflowName(workflows.map(draftRowFromGenerated), input.workflowName);
        }
      }
    } catch {
      // fall through to the local fallback
    }
  }

  // Fallback: one draft per human-provided doc.
  const services = input.services.map((s) => ({ name: s.name, version: s.version ?? null }));
  const rows = input.docs.slice(0, input.count).map((doc) => ({
    name: focus ? `${doc.title}: ${focus}` : doc.title,
    description: firstSentence(doc.text),
    difficulty: "medium",
    task_prompt: focus ? `${doc.text}\n\nFocus this workflow on: ${focus}` : doc.text,
    draft: {
      name: focus ? `${doc.title}: ${focus}` : doc.title,
      description: firstSentence(doc.text),
      task_prompt: focus ? `${doc.text}\n\nFocus this workflow on: ${focus}` : doc.text,
      services,
      focus: focus ?? null,
      focus_alignment_reason: focus
        ? `The user explicitly asked generation to focus on ${focus}.`
        : null,
      source_doc: doc.url ?? doc.title,
    },
  }));
  return applyWorkflowName(rows, input.workflowName);
}
