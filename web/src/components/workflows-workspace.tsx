"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  AlertCircle,
  GitBranch,
  GitFork,
  Loader2,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  assignWorkflowToSandboxes,
  createRun,
  deleteWorkflow,
  generateWorkflows,
  listSandboxes,
  listWorkflows,
  removeWorkflowFromSandbox,
  updateWorkflow,
  type DocInput,
  type Workflow,
  type WorkflowGenerationResult,
} from "@/lib/sandbox-api";
import type { Sandbox } from "@/lib/mock-data";

export function WorkflowsWorkspace() {
  const [workflows, setWorkflows] = React.useState<Workflow[] | null>(null);
  const [sandboxes, setSandboxes] = React.useState<Sandbox[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      const [wf, sb] = await Promise.all([listWorkflows(), listSandboxes()]);
      setWorkflows(wf);
      setSandboxes(sb);
    } catch {
      setError("Could not load workflows.");
    }
  }, []);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const loading = workflows === null && !error;
  const workflowsByRepo = React.useMemo(() => {
    const sandboxById = new Map(sandboxes.map((sandbox) => [sandbox.id, sandbox]));
    const groups = new Map<string, { repo: string; workflows: Workflow[] }>();
    for (const workflow of workflows ?? []) {
      const sandbox = sandboxById.get(workflow.sandboxId);
      const repo = sandbox?.repo ?? "Unknown repository";
      const group = groups.get(repo) ?? { repo, workflows: [] };
      group.workflows.push(workflow);
      groups.set(repo, group);
    }
    return Array.from(groups.values()).sort((a, b) => a.repo.localeCompare(b.repo));
  }, [sandboxes, workflows]);

  return (
    <AppShell>
      <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-normal text-foreground">Workflows</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Reuse generated agent tasks across sandboxes without losing sandbox-specific runs.
            </p>
          </div>
          <GenerateWorkflowSheet sandboxes={sandboxes} onGenerated={load} />
        </div>

        {error ? (
          <ErrorState message={error} onRetry={load} />
        ) : loading ? (
          <ListSkeleton />
        ) : workflowsByRepo.length > 0 ? (
          <div className="grid gap-4">
            {workflowsByRepo.map((group) => (
              <section key={group.repo} className="space-y-2">
                <div className="flex items-center gap-2 px-1 text-sm font-medium text-muted-foreground">
                  <GitFork className="size-4" />
                  {group.repo}
                </div>
                <div className="grid gap-3">
                  {group.workflows.map((workflow) => (
                    <WorkflowCard
                      key={workflow.id}
                      workflow={workflow}
                      sandbox={sandboxes.find((item) => item.id === workflow.sandboxId) ?? null}
                      sandboxes={sandboxes}
                      onChanged={load}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>
        ) : (
          <EmptyState sandboxes={sandboxes} onGenerated={load} />
        )}
      </main>
    </AppShell>
  );
}

export function WorkflowCard({
  workflow,
  sandbox,
  sandboxes,
  onChanged,
  presentation = "card",
}: {
  workflow: Workflow;
  sandbox: Sandbox | null;
  sandboxes: Sandbox[];
  onChanged: () => void | Promise<void>;
  presentation?: "card" | "inline";
}) {
  const router = useRouter();
  const [running, setRunning] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);

  async function run() {
    const assignmentId = workflow.assignmentId ?? workflow.id;
    if (!workflow.sandboxId || !assignmentId) {
      toast.error("Assign this workflow to a sandbox before running it.");
      return;
    }
    setRunning(true);
    try {
      const created = await createRun(workflow.sandboxId, assignmentId);
      toast.success("Run started");
      router.push(`/runs/${created.id}`);
    } catch {
      toast.error("Could not start run.");
      setRunning(false);
    }
  }

  async function remove() {
    const confirmed = window.confirm(`Delete workflow "${workflow.name}"?`);
    if (!confirmed) return;
    setDeleting(true);
    try {
      await deleteWorkflow(workflow.canonicalId ?? workflow.id);
      toast.success("Workflow deleted");
      await onChanged();
    } catch {
      toast.error("Could not delete workflow.");
    } finally {
      setDeleting(false);
    }
  }

  const content = (
    <div className="flex flex-col gap-3 p-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-foreground">{workflow.name}</span>
            {workflow.difficulty && (
              <Badge variant="secondary" className="h-5 rounded-md px-1.5 text-[11px]">
                {workflow.difficulty}
              </Badge>
            )}
          </div>
          {workflow.description && (
            <p className="mt-1 text-sm text-muted-foreground">{workflow.description}</p>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            {sandbox && (
              <span className="inline-flex items-center gap-1.5">
                <GitBranch className="size-3.5" />
                {sandbox.name} · {sandbox.branch}
              </span>
            )}
            {typeof workflow.assignedSandboxCount === "number" && (
              <span>
                {workflow.assignedSandboxCount} sandbox{workflow.assignedSandboxCount === 1 ? "" : "es"}
              </span>
            )}
            <span>{new Date(workflow.createdAt).toLocaleString()}</span>
          </div>
          {workflow.focus && <p className="mt-2 text-xs text-muted-foreground">Focus: {workflow.focus}</p>}
          {workflow.noveltyReason && (
            <p className="mt-1 text-xs text-muted-foreground">Novelty: {workflow.noveltyReason}</p>
          )}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {workflow.services.map((service) => (
              <Badge key={service} variant="outline" className="h-6 rounded-md bg-background px-2 font-normal">
                {service}
              </Badge>
            ))}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <EditWorkflowSheet workflow={workflow} onSaved={onChanged} />
          <AssignWorkflowSheet workflow={workflow} sandboxes={sandboxes} onAssigned={onChanged} />
          {sandbox && (
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                await removeWorkflowFromSandbox(sandbox.id, workflow.canonicalId ?? workflow.id);
                toast.success("Workflow removed from sandbox");
                await onChanged();
              }}
            >
              <X />
              Remove
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={remove} disabled={deleting}>
            {deleting ? <Loader2 className="animate-spin" /> : <Trash2 />}
            Delete
          </Button>
          <Button variant="outline" size="sm" onClick={run} disabled={running}>
            {running ? <Loader2 className="animate-spin" /> : <Play />}
            Run
          </Button>
        </div>
      </div>
  );

  if (presentation === "inline") {
    return <div className="rounded-lg border bg-card">{content}</div>;
  }

  return (
    <Card className="rounded-lg shadow-none">
      <CardContent className="p-0">
        {content}
      </CardContent>
    </Card>
  );
}

function AssignWorkflowSheet({
  workflow,
  sandboxes,
  onAssigned,
}: {
  workflow: Workflow;
  sandboxes: Sandbox[];
  onAssigned: () => void | Promise<void>;
}) {
  const [open, setOpen] = React.useState(false);
  const [selected, setSelected] = React.useState<string[]>([]);
  const [saving, setSaving] = React.useState(false);
  const assigned = new Set(workflow.sandboxIds ?? (workflow.sandboxId ? [workflow.sandboxId] : []));
  const available = sandboxes.filter((sandbox) => !assigned.has(sandbox.id));

  function toggle(id: string, checked: boolean) {
    setSelected((current) => checked ? [...current, id] : current.filter((item) => item !== id));
  }

  async function assign() {
    const canonicalId = workflow.canonicalId ?? workflow.id;
    if (selected.length === 0) return;
    setSaving(true);
    try {
      await assignWorkflowToSandboxes(canonicalId, selected);
      toast.success("Workflow assigned");
      setOpen(false);
      setSelected([]);
      await onAssigned();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not assign workflow.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={<Button variant="outline" size="sm" />}>
        <Plus />
        Assign
      </SheetTrigger>
      <SheetContent className="w-full border-l bg-card p-0 sm:max-w-none md:!w-[460px]">
        <SheetHeader className="border-b px-6 py-5">
          <SheetTitle>Assign workflow</SheetTitle>
          <SheetDescription>Add this reusable workflow to other sandboxes.</SheetDescription>
        </SheetHeader>
        <div className="flex-1 space-y-3 overflow-y-auto px-6 py-5">
          {available.length === 0 ? (
            <p className="text-sm text-muted-foreground">This workflow is already assigned to every sandbox.</p>
          ) : (
            available.map((sandbox) => (
              <label
                key={sandbox.id}
                className="flex cursor-pointer items-start gap-3 rounded-lg border bg-card p-3"
              >
                <Checkbox
                  checked={selected.includes(sandbox.id)}
                  onCheckedChange={(checked) => toggle(sandbox.id, checked === true)}
                />
                <span className="min-w-0">
                  <span className="block text-sm font-medium">{sandbox.name}</span>
                  <span className="block text-xs text-muted-foreground">
                    {sandbox.repo} · {sandbox.branch}
                  </span>
                </span>
              </label>
            ))
          )}
        </div>
        <SheetFooter className="border-t px-6 py-4">
          <Button onClick={assign} disabled={saving || selected.length === 0} className="w-full">
            {saving ? <Loader2 className="animate-spin" /> : <Plus />}
            {saving ? "Assigning…" : "Assign to selected sandboxes"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function EditWorkflowSheet({
  workflow,
  onSaved,
}: {
  workflow: Workflow;
  onSaved: () => void | Promise<void>;
}) {
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState(workflow.name);
  const [description, setDescription] = React.useState(workflow.description ?? "");
  const [difficulty, setDifficulty] = React.useState(workflow.difficulty ?? "");
  const [taskPrompt, setTaskPrompt] = React.useState(workflow.taskPrompt ?? "");
  const [services, setServices] = React.useState(workflow.services.join(", "));
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) return;
    setName(workflow.name);
    setDescription(workflow.description ?? "");
    setDifficulty(workflow.difficulty ?? "");
    setTaskPrompt(workflow.taskPrompt ?? "");
    setServices(workflow.services.join(", "));
    setError(null);
  }

  async function save() {
    const cleanName = name.trim();
    if (!cleanName) {
      setError("Workflow name is required.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await updateWorkflow(workflow.canonicalId ?? workflow.id, {
        name: cleanName,
        description,
        difficulty,
        taskPrompt,
        services: services
          .split(",")
          .map((service) => service.trim())
          .filter(Boolean),
      });
      toast.success("Workflow updated");
      setOpen(false);
      await onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update workflow.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetTrigger render={<Button variant="outline" size="sm" />}>
        <Pencil />
        Edit
      </SheetTrigger>
      <SheetContent className="w-full border-l bg-card p-0 sm:max-w-none md:!w-[560px]">
        <SheetHeader className="border-b px-6 py-5">
          <SheetTitle>Edit workflow</SheetTitle>
          <SheetDescription>Update the task description, prompt, and service tags.</SheetDescription>
        </SheetHeader>
        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
              {error}
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor={`workflow-name-${workflow.id}`}>Name</Label>
            <Input
              id={`workflow-name-${workflow.id}`}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`workflow-description-${workflow.id}`}>Description</Label>
            <textarea
              id={`workflow-description-${workflow.id}`}
              className="min-h-[88px] w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor={`workflow-prompt-${workflow.id}`}>Task prompt</Label>
            <textarea
              id={`workflow-prompt-${workflow.id}`}
              className="min-h-[140px] w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={taskPrompt}
              onChange={(event) => setTaskPrompt(event.target.value)}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor={`workflow-difficulty-${workflow.id}`}>Difficulty</Label>
              <Input
                id={`workflow-difficulty-${workflow.id}`}
                value={difficulty}
                onChange={(event) => setDifficulty(event.target.value)}
                placeholder="easy, medium, hard"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={`workflow-services-${workflow.id}`}>Services</Label>
              <Input
                id={`workflow-services-${workflow.id}`}
                value={services}
                onChange={(event) => setServices(event.target.value)}
                placeholder="Stripe, Gmail"
              />
            </div>
          </div>
        </div>
        <SheetFooter className="border-t px-6 py-4">
          <Button onClick={save} disabled={saving} className="w-full">
            {saving ? <Loader2 className="animate-spin" /> : <Save />}
            {saving ? "Saving…" : "Save workflow"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

export function GenerateWorkflowSheet({
  sandboxes,
  onGenerated,
  trigger,
}: {
  sandboxes: Sandbox[];
  onGenerated: () => void | Promise<void>;
  trigger?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  const [sandboxId, setSandboxId] = React.useState("");
  const [workflowName, setWorkflowName] = React.useState("");
  const [focus, setFocus] = React.useState("");
  const [docs, setDocs] = React.useState<DocInput[]>([{ title: "", text: "" }]);
  const [count, setCount] = React.useState(3);
  const [generating, setGenerating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [lastResult, setLastResult] = React.useState<WorkflowGenerationResult | null>(null);

  React.useEffect(() => {
    if (!open || sandboxId || !sandboxes[0]) return;
    const timer = window.setTimeout(() => {
      setSandboxId(sandboxes[0].id);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [open, sandboxId, sandboxes]);

  const sandbox = sandboxes.find((item) => item.id === sandboxId);
  // Services come from the sandbox's twins ({id: version} map).
  const services: { name: string; version: string | null }[] = sandbox?.twinVersions
    ? Object.entries(sandbox.twinVersions).map(([name, version]) => ({ name, version }))
    : [];

  function setDoc(index: number, patch: Partial<DocInput>) {
    setDocs((current) => current.map((doc, i) => (i === index ? { ...doc, ...patch } : doc)));
  }

  async function generate() {
    const filled = docs.filter((doc) => doc.title.trim() && doc.text.trim());
    if (!sandboxId) return setError("Pick a sandbox first.");
    if (filled.length === 0) return setError("Add at least one doc with a title and text.");
    setGenerating(true);
    setError(null);
    setLastResult(null);
    try {
      const result = await generateWorkflows({
        sandboxId,
        workflowName,
        focus,
        docs: filled,
        services,
        count,
      });
      const createdCount = result.workflows.length;
      const skippedCount = result.skipped.length;
      setLastResult(result);
      if (createdCount > 0) {
        toast.success(
          `Generated ${createdCount} workflow${createdCount === 1 ? "" : "s"}`,
          skippedCount > 0
            ? { description: `${skippedCount} duplicate candidate${skippedCount === 1 ? "" : "s"} filtered out.` }
            : undefined,
        );
        setWorkflowName("");
        setFocus("");
        setDocs([{ title: "", text: "" }]);
      }
      await onGenerated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate workflows.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger render={trigger ? (trigger as React.ReactElement) : <Button size="lg" />}>
        {trigger ? undefined : (
          <>
            <Sparkles />
            Generate workflows
          </>
        )}
      </SheetTrigger>
      <SheetContent className="w-full border-l bg-card p-0 sm:max-w-none md:!w-[560px]">
        <SheetHeader className="border-b px-6 py-5">
          <SheetTitle>Generate workflows</SheetTitle>
          <SheetDescription>
            Workflows are generated from your docs and the twins in the selected sandbox.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
              {error}
            </div>
          )}
          {lastResult && (
            <GenerationResultPanel result={lastResult} requestedCount={count} />
          )}

          <div className="space-y-2">
            <Label htmlFor="wf-sandbox">Sandbox</Label>
            <Select value={sandboxId} onValueChange={(value) => setSandboxId(String(value ?? ""))}>
              <SelectTrigger id="wf-sandbox" className="h-10 w-full">
                <SelectValue placeholder="Select a sandbox" />
              </SelectTrigger>
              <SelectContent align="start">
                {sandboxes.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.name} · {item.repo}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {sandbox && (
              <p className="text-xs text-muted-foreground">
                Twins: {sandbox.twins.length > 0 ? sandbox.twins.join(", ") : "none"}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="workflow-name">Workflow name</Label>
            <Input
              id="workflow-name"
              placeholder={count === 1 ? "Refund support flow" : "Refund support flow set"}
              value={workflowName}
              onChange={(event) => setWorkflowName(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              For multiple workflows this is used as a numbered prefix.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="workflow-focus">Focus</Label>
            <Input
              id="workflow-focus"
              placeholder="Billing recovery, OAuth setup, multi-service onboarding..."
              value={focus}
              onChange={(event) => setFocus(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Optional. Use this to target a product area, risk, integration, or failure mode.
            </p>
            <div className="flex flex-wrap gap-2">
              {[
                "Happy paths",
                "Edge cases",
                "Multi-service workflows",
                "Failure recovery",
                "Security-sensitive flows",
                "Regression coverage",
              ].map((item) => (
                <Button
                  key={item}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setFocus(item)}
                >
                  {item}
                </Button>
              ))}
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <Label>Docs</Label>
                <p className="mt-1 text-xs text-muted-foreground">
                  Paste product docs or write the context an agent needs. This is the human input the
                  generator builds on.
                </p>
              </div>
            </div>
            {docs.map((doc, index) => (
              <div key={index} className="space-y-2 rounded-lg border bg-card p-3">
                <div className="flex items-center gap-2">
                  <Input
                    placeholder="Title (e.g. Refund flow)"
                    value={doc.title}
                    onChange={(event) => setDoc(index, { title: event.target.value })}
                  />
                  {docs.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => setDocs((current) => current.filter((_, i) => i !== index))}
                      aria-label="Remove doc"
                    >
                      <X />
                    </Button>
                  )}
                </div>
                <textarea
                  className="min-h-[96px] w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder="Describe the capability, steps, and expected outcome…"
                  value={doc.text}
                  onChange={(event) => setDoc(index, { text: event.target.value })}
                />
                <Input
                  placeholder="Source URL (optional)"
                  value={doc.url ?? ""}
                  onChange={(event) => setDoc(index, { url: event.target.value })}
                />
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setDocs((current) => [...current, { title: "", text: "" }])}
            >
              <Plus />
              Add doc
            </Button>
          </div>

          <div className="space-y-2">
            <Label htmlFor="wf-count">Number of workflows</Label>
            <Input
              id="wf-count"
              type="number"
              min={1}
              max={12}
              value={count}
              onChange={(event) => setCount(Number(event.target.value) || 1)}
              className="w-24"
            />
          </div>
        </div>

        <SheetFooter className="border-t px-6 py-4">
          <Button onClick={generate} disabled={generating} className="w-full">
            {generating ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {generating ? "Generating…" : "Generate"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function GenerationResultPanel({
  result,
  requestedCount,
}: {
  result: WorkflowGenerationResult;
  requestedCount: number;
}) {
  const createdCount = result.workflows.length;
  const skippedCount = result.skipped.length;
  const partial = createdCount > 0 && createdCount < requestedCount;
  const tone = createdCount === 0 || partial ? "border-amber-200 bg-amber-50 text-amber-950" : "border-emerald-200 bg-emerald-50 text-emerald-950";

  return (
    <div className={`rounded-lg border px-3 py-3 text-sm ${tone}`}>
      <div className="font-medium">
        {createdCount === 0
          ? "No novel workflows generated"
          : partial
            ? `Generated ${createdCount} of ${requestedCount} requested workflows`
            : `Generated ${createdCount} workflow${createdCount === 1 ? "" : "s"}`}
      </div>
      {result.detail && <p className="mt-1 opacity-85">{result.detail}</p>}
      {skippedCount > 0 && (
        <div className="mt-3 space-y-2">
          <div className="text-xs font-medium uppercase tracking-normal opacity-75">
            Filtered duplicates
          </div>
          {result.skipped.slice(0, 4).map((item, index) => (
            <div key={`${item.name}-${index}`} className="rounded-md bg-background/70 px-2 py-1.5">
              <div className="font-medium">{item.name}</div>
              <div className="mt-0.5 text-xs opacity-80">
                {item.matchedWorkflowName ? `Similar to ${item.matchedWorkflowName}. ` : ""}
                {item.reason}
              </div>
            </div>
          ))}
          {skippedCount > 4 && (
            <div className="text-xs opacity-75">
              {skippedCount - 4} more duplicate candidate{skippedCount - 4 === 1 ? "" : "s"} filtered.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function EmptyState({
  sandboxes,
  onGenerated,
}: {
  sandboxes: Sandbox[];
  onGenerated: () => void | Promise<void>;
}) {
  return (
    <Card className="rounded-lg border-dashed shadow-none">
      <CardContent className="flex min-h-[320px] flex-col items-center justify-center p-8 text-center">
        <div className="flex size-11 items-center justify-center rounded-lg bg-accent text-primary">
          <GitBranch className="size-5" />
        </div>
        <h2 className="mt-4 text-lg font-semibold">No workflows yet</h2>
        <p className="mt-2 max-w-sm text-sm text-muted-foreground">
          Generate workflows from your docs and the twins in a sandbox.
        </p>
        <div className="mt-5">
          <GenerateWorkflowSheet
            sandboxes={sandboxes}
            onGenerated={onGenerated}
            trigger={
              <Button>
                <Sparkles />
                Generate workflows
              </Button>
            }
          />
        </div>
      </CardContent>
    </Card>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className="rounded-lg border-red-200 bg-red-50 shadow-none">
      <CardContent className="flex min-h-[220px] flex-col items-center justify-center p-8 text-center">
        <AlertCircle className="size-9 text-red-600" />
        <p className="mt-4 text-sm text-red-800">{message}</p>
        <Button className="mt-5" variant="outline" onClick={onRetry}>
          <RefreshCw />
          Retry
        </Button>
      </CardContent>
    </Card>
  );
}

function ListSkeleton() {
  return (
    <div className="grid gap-3">
      {Array.from({ length: 3 }).map((_, index) => (
        <Skeleton key={index} className="h-24 w-full rounded-lg" />
      ))}
    </div>
  );
}
