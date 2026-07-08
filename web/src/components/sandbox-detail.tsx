"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  Boxes,
  Clock3,
  Database,
  EyeOff,
  KeyRound,
  Loader2,
  GitBranch,
  GitFork,
  Sparkles,
  RotateCcw,
  Save,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  generateSimulationScenario,
  deleteSandboxEnvVar,
  getSimulationScenario,
  getSandbox,
  listSandboxEnvVars,
  listSandboxWorkflows,
  listSandboxOptions,
  saveSimulationScenario,
  saveSandboxEnvVars,
  updateSandboxTwins,
  type SandboxEnvVar,
  type SandboxOptionData,
  type SimulationProfile,
  type SimulationScenario,
  type Workflow,
} from "@/lib/sandbox-api";
import { useSandboxStore } from "@/components/sandbox-store";
import { GenerateWorkflowSheet, WorkflowCard } from "@/components/workflows-workspace";
import { twinIconMap, twinOptions, type Sandbox, type SandboxStatus, type TwinOption } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

export function SandboxDetail({ id }: { id: string }) {
  const [sandbox, setSandbox] = React.useState<Sandbox | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSandbox(await getSandbox(id));
    } catch {
      setError("This sandbox could not be found.");
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

  return (
    <AppShell>
      <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <Link
          href="/sandboxes"
          className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Sandboxes
        </Link>

        {loading ? (
          <DetailSkeleton />
        ) : error || !sandbox ? (
          <Card className="rounded-lg border-red-200 bg-red-50 shadow-none">
            <CardContent className="flex min-h-[240px] flex-col items-center justify-center p-8 text-center">
              <AlertCircle className="size-9 text-red-600" />
              <h2 className="mt-4 text-lg font-semibold text-red-950">Sandbox unavailable</h2>
              <p className="mt-2 text-sm text-red-800">{error ?? "Not found."}</p>
              <Button className="mt-5" variant="outline" onClick={load}>
                <RefreshCw />
                Retry
              </Button>
            </CardContent>
          </Card>
        ) : (
          <SandboxBody sandbox={sandbox} />
        )}
      </main>
    </AppShell>
  );
}

function SandboxBody({ sandbox: initialSandbox }: { sandbox: Sandbox }) {
  const [sandbox, setSandbox] = React.useState(initialSandbox);
  const [editing, setEditing] = React.useState(false);

  // Prefer the {id: version} map (DB-backed) so we can show pinned versions;
  // fall back to bare twin names for mock sandboxes.
  const twins = sandbox.twinVersions
    ? Object.entries(sandbox.twinVersions).map(([id, version]) => ({
        name: twinOptions.find((twin) => twin.id === id)?.name ?? id,
        version,
      }))
    : sandbox.twins.map((name) => ({ name, version: null as string | null }));

  const stats = [
    { label: "Workflows", value: String(sandbox.workflowCount), icon: Boxes },
    { label: "Status", value: sandbox.status, icon: Activity },
    { label: "Last run", value: sandbox.lastRun, icon: Clock3 },
  ];

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-normal text-foreground">
              {sandbox.name}
            </h1>
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
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label} className="rounded-lg shadow-none">
              <CardContent className="flex items-center justify-between p-4">
                <div className="min-w-0">
                  <div className="text-sm text-muted-foreground">{stat.label}</div>
                  <div className="mt-1 truncate text-lg font-semibold">{stat.value}</div>
                </div>
                <div className="flex size-9 items-center justify-center rounded-lg bg-accent text-primary">
                  <Icon className="size-4" />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card className="rounded-lg shadow-none">
        <CardHeader className="flex flex-row items-center justify-between border-b">
          <CardTitle className="text-base">Twins</CardTitle>
          <Button variant="outline" size="sm" onClick={() => setEditing((current) => !current)}>
            {editing ? "Done" : "Edit twins"}
          </Button>
        </CardHeader>
        <CardContent className="p-4">
          {editing ? (
            <TwinEditor sandbox={sandbox} onSaved={setSandbox} />
          ) : twins.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {twins.map((twin) => {
                const Icon =
                  twinIconMap[twin.name as keyof typeof twinIconMap] ?? twinIconMap.default;
                return (
                  <Badge
                    key={twin.name}
                    variant="outline"
                    className="h-8 gap-1.5 rounded-md bg-background px-2.5 font-normal"
                  >
                    <Icon className="size-3.5 text-muted-foreground" />
                    {twin.name}
                    {twin.version && (
                      <span className="text-muted-foreground">· {twin.version}</span>
                    )}
                  </Badge>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No twins selected for this sandbox.</p>
          )}
        </CardContent>
      </Card>

      <SandboxWorkflowsCard sandbox={sandbox} />
      <EnvVarsCard sandbox={sandbox} />

      <div id="simulation-data" className="scroll-mt-6">
        <SimulationDataCard sandbox={sandbox} />
      </div>
    </>
  );
}

function SandboxWorkflowsCard({ sandbox }: { sandbox: Sandbox }) {
  const [workflows, setWorkflows] = React.useState<Workflow[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setError(null);
    try {
      setWorkflows(await listSandboxWorkflows(sandbox.id));
    } catch {
      setError("Could not load workflows for this sandbox.");
    }
  }, [sandbox.id]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <Card className="rounded-lg shadow-none">
      <CardHeader className="flex flex-row items-center justify-between border-b">
        <CardTitle className="text-base">Workflows</CardTitle>
        <GenerateWorkflowSheet
          sandboxes={[sandbox]}
          onGenerated={load}
          trigger={
            <Button size="sm">
              <Sparkles />
              Generate
            </Button>
          }
        />
      </CardHeader>
      <CardContent className="p-4">
        {error ? (
          <p className="text-sm text-red-700">{error}</p>
        ) : workflows === null ? (
          <div className="grid gap-2">
            <Skeleton className="h-14 rounded-lg" />
            <Skeleton className="h-14 rounded-lg" />
          </div>
        ) : workflows.length > 0 ? (
          <div className="grid gap-2">
            {workflows.map((workflow) => (
              <WorkflowCard
                key={workflow.id}
                workflow={workflow}
                sandbox={sandbox}
                sandboxes={[sandbox]}
                onChanged={load}
                presentation="inline"
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed p-5 text-center">
            <p className="text-sm font-medium">No workflows assigned yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Generate workflows here so they inherit this sandbox&apos;s docs, repo, branch, and twins.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

type EnvDraft = {
  key: string;
  value: string;
};

function EnvVarsCard({ sandbox }: { sandbox: Sandbox }) {
  const [envVars, setEnvVars] = React.useState<SandboxEnvVar[]>([]);
  const [drafts, setDrafts] = React.useState<EnvDraft[]>([{ key: "", value: "" }]);
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [deletingKey, setDeletingKey] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEnvVars(await listSandboxEnvVars(sandbox.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load env vars.");
    } finally {
      setLoading(false);
    }
  }, [sandbox.id]);

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  function setDraft(index: number, patch: Partial<EnvDraft>) {
    setDrafts((current) => current.map((draft, i) => (i === index ? { ...draft, ...patch } : draft)));
  }

  async function save() {
    const filled = drafts.filter((draft) => draft.key.trim() || draft.value);
    if (filled.length === 0) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await saveSandboxEnvVars(sandbox.id, filled);
      setEnvVars((current) => {
        const map = new Map(current.map((item) => [item.key, item]));
        for (const item of saved) map.set(item.key, item);
        return Array.from(map.values()).sort((a, b) => a.key.localeCompare(b.key));
      });
      setDrafts([{ key: "", value: "" }]);
      toast.success("Environment variables saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save env vars.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(key: string) {
    setDeletingKey(key);
    setError(null);
    try {
      await deleteSandboxEnvVar(sandbox.id, key);
      setEnvVars((current) => current.filter((item) => item.key !== key));
      toast.success(`${key} removed`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete env var.");
    } finally {
      setDeletingKey(null);
    }
  }

  return (
    <Card className="rounded-lg shadow-none">
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="size-4 text-primary" />
          Environment variables
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
            {error}
          </div>
        )}
        <div className="space-y-2">
          <div className="text-sm font-medium">Saved keys</div>
          {loading ? (
            <Skeleton className="h-16 w-full rounded-lg" />
          ) : envVars.length > 0 ? (
            <div className="divide-y rounded-lg border">
              {envVars.map((item) => (
                <div key={item.key} className="flex items-center justify-between gap-3 p-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      <EyeOff className="size-3.5 text-muted-foreground" />
                      {item.key}
                    </div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Value hidden after save · Updated {new Date(item.updatedAt).toLocaleString()}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => void remove(item.key)}
                    disabled={deletingKey === item.key}
                    aria-label={`Delete ${item.key}`}
                  >
                    {deletingKey === item.key ? <Loader2 className="animate-spin" /> : <Trash2 />}
                  </Button>
                </div>
              ))}
            </div>
          ) : (
            <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
              No environment variables saved for this sandbox.
            </p>
          )}
        </div>

        <div className="space-y-3">
          <div>
            <div className="text-sm font-medium">Add or replace variables</div>
            <p className="mt-1 text-xs text-muted-foreground">
              Values are write-only in the UI. Re-enter a key to replace its stored value.
            </p>
          </div>
          {drafts.map((draft, index) => (
            <div key={index} className="grid gap-2 sm:grid-cols-[minmax(180px,1fr)_minmax(220px,1.2fr)_40px]">
              <Input
                placeholder="OPENAI_API_KEY"
                value={draft.key}
                onChange={(event) => setDraft(index, { key: event.target.value })}
                autoCapitalize="none"
                spellCheck={false}
              />
              <Input
                type="password"
                placeholder="Value"
                value={draft.value}
                onChange={(event) => setDraft(index, { value: event.target.value })}
                autoComplete="new-password"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setDrafts((current) => current.filter((_, i) => i !== index))}
                disabled={drafts.length === 1}
                aria-label="Remove env var row"
              >
                <Trash2 />
              </Button>
            </div>
          ))}
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setDrafts((current) => [...current, { key: "", value: "" }])}
            >
              Add variable
            </Button>
            <Button onClick={save} disabled={saving}>
              {saving ? <Loader2 className="animate-spin" /> : <Save />}
              Save variables
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function latestVersion(twin: TwinOption) {
  return twin.versions[twin.versions.length - 1] ?? "";
}

function TwinEditor({
  sandbox,
  onSaved,
}: {
  sandbox: Sandbox;
  onSaved: (sandbox: Sandbox) => void;
}) {
  const { setSandboxes } = useSandboxStore();
  const [optionData, setOptionData] = React.useState<SandboxOptionData | null>(null);
  const [selected, setSelected] = React.useState<Record<string, string>>(sandbox.twinVersions ?? {});
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let alive = true;
    listSandboxOptions()
      .then((data) => {
        if (alive) setOptionData(data);
      })
      .catch(() => {
        if (alive) setError("Could not load available twins.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  function toggleTwin(twin: TwinOption, checked: boolean) {
    setSelected((current) => {
      const next = { ...current };
      if (checked) {
        next[twin.id] = current[twin.id] || latestVersion(twin);
      } else {
        delete next[twin.id];
      }
      return next;
    });
  }

  function setTwinVersion(id: string, version: string) {
    setSelected((current) => ({ ...current, [id]: version }));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateSandboxTwins(sandbox.id, selected);
      onSaved(updated);
      setSandboxes((current) =>
        current ? current.map((item) => (item.id === updated.id ? updated : item)) : current,
      );
      toast.success("Twins updated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update twins.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <Skeleton className="h-48 w-full rounded-lg" />;
  }

  const twins = optionData?.twins ?? twinOptions;

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
          {error}
        </div>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        {twins.map((twin) => {
          const checked = twin.id in selected;
          const version = selected[twin.id] ?? latestVersion(twin);
          return (
            <label
              key={twin.id}
              className={cn(
                "flex min-h-[92px] items-start gap-3 rounded-lg border bg-card p-3 transition-colors",
                checked ? "border-primary/40 bg-accent/60" : "hover:bg-muted/70",
              )}
            >
              <Checkbox
                checked={checked}
                onCheckedChange={(next) => toggleTwin(twin, next === true)}
                className="mt-0.5"
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className={cn("size-2 rounded-full", twin.tone)} />
                  <span className="text-sm font-medium">{twin.name}</span>
                </span>
                <span className="mt-1 block text-xs text-muted-foreground">{twin.description}</span>
                {checked && (
                  <span className="mt-3 block">
                    <Label className="sr-only">{twin.name} version</Label>
                    <Select value={version} onValueChange={(value) => setTwinVersion(twin.id, String(value))}>
                      <SelectTrigger className="h-8 w-36">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent align="start">
                        {twin.versions.map((item) => (
                          <SelectItem key={item} value={item}>
                            {item}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </span>
                )}
              </span>
            </label>
          );
        })}
      </div>
      <div className="flex justify-end">
        <Button onClick={save} disabled={saving}>
          {saving ? <Loader2 className="animate-spin" /> : <Save />}
          Save twins
        </Button>
      </div>
    </div>
  );
}

function SimulationDataCard({ sandbox }: { sandbox: Sandbox }) {
  const [profile, setProfile] = React.useState<SimulationProfile>("baseline");
  const [scenarioName, setScenarioName] = React.useState("Default scenario");
  const [dataDescription, setDataDescription] = React.useState("");
  const [scenarioText, setScenarioText] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [generating, setGenerating] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let alive = true;
    const timer = window.setTimeout(() => {
      getSimulationScenario(sandbox.id)
        .then((scenario) => {
          if (!alive || !scenario) return;
          setScenarioName(scenario.name ?? "Default scenario");
          setProfile(scenario.profile);
          setScenarioText(JSON.stringify(scenario, null, 2));
        })
        .catch((err) => {
          if (alive) setError(err instanceof Error ? err.message : "Could not load simulation data.");
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }, 0);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [sandbox.id]);

  async function generate() {
    setGenerating(true);
    setError(null);
    try {
      const scenario = await generateSimulationScenario(sandbox.id, profile, dataDescription.trim());
      scenario.name = scenarioName.trim() || scenario.name;
      setScenarioText(JSON.stringify(scenario, null, 2));
      toast.success(dataDescription.trim() ? "Simulation data generated from description" : "Simulation data generated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate simulation data.");
    } finally {
      setGenerating(false);
    }
  }

  function save() {
    setSaving(true);
    setError(null);
    try {
      const parsed = JSON.parse(scenarioText) as SimulationScenario;
      if (!Array.isArray(parsed.seeds)) {
        throw new Error("Scenario JSON must include a seeds array.");
      }
      void saveSimulationScenario(sandbox.id, {
        ...parsed,
        name: scenarioName.trim() || parsed.name || "Default scenario",
      })
        .then((saved) => {
          setScenarioName(saved.name ?? "Default scenario");
          setProfile(saved.profile);
          setScenarioText(JSON.stringify(saved, null, 2));
          toast.success("Simulation data saved");
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Could not save simulation data.");
        })
        .finally(() => setSaving(false));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scenario JSON is invalid.");
      setSaving(false);
    }
  }

  function reset() {
    setScenarioText("");
    setError(null);
  }

  const seedCount = React.useMemo(() => {
    try {
      const parsed = JSON.parse(scenarioText) as SimulationScenario;
      return parsed.seeds.reduce(
        (total, seed) =>
          total +
          Object.values(seed.resources).reduce(
            (resourceTotal, rows) => resourceTotal + (Array.isArray(rows) ? rows.length : 0),
            0,
          ),
        0,
      );
    } catch {
      return 0;
    }
  }, [scenarioText]);

  return (
    <Card className="rounded-lg shadow-none">
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2 text-base">
          <Database className="size-4 text-primary" />
          Simulation data
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 p-4">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
            {error}
          </div>
        )}
        {loading && <Skeleton className="h-20 w-full rounded-lg" />}
        <div className="space-y-2">
          <Label htmlFor="simulation-description">Describe the data you want (optional)</Label>
          <textarea
            id="simulation-description"
            className="min-h-[72px] w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={dataDescription}
            onChange={(event) => setDataDescription(event.target.value)}
            placeholder="e.g. a #support channel with 5 customer messages about password resets and billing, plus a #general channel with some chatter"
          />
          <p className="text-xs text-muted-foreground">
            With a description, Generate uses an LLM to seed the twins. Leave blank to use the
            registry seed and the profile below.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-[minmax(220px,1fr)_220px] sm:items-end">
          <div className="space-y-2">
            <Label htmlFor="simulation-name">Scenario name</Label>
            <input
              id="simulation-name"
              className="h-10 w-full rounded-md border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={scenarioName}
              onChange={(event) => setScenarioName(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="simulation-profile">Profile</Label>
            <Select value={profile} onValueChange={(value) => setProfile(value as SimulationProfile)}>
              <SelectTrigger id="simulation-profile" className="h-10">
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="start">
                <SelectItem value="baseline">Baseline seed</SelectItem>
                <SelectItem value="busy">Busy workspace</SelectItem>
                <SelectItem value="edge">Edge cases</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-wrap gap-2 sm:justify-end">
            <Button variant="outline" onClick={reset} disabled={!scenarioText}>
              <RotateCcw />
              Reset
            </Button>
            <Button variant="outline" onClick={generate} disabled={generating}>
              {generating ? <Loader2 className="animate-spin" /> : <Database />}
              Generate
            </Button>
            <Button onClick={save} disabled={saving || !scenarioText}>
              {saving ? <Loader2 className="animate-spin" /> : <Save />}
              Save scenario
            </Button>
          </div>
        </div>
        <textarea
          className="min-h-[260px] w-full rounded-md border bg-background px-3 py-2 font-mono text-xs outline-none focus-visible:ring-2 focus-visible:ring-ring"
          value={scenarioText}
          onChange={(event) => setScenarioText(event.target.value)}
          placeholder="Generate a scenario from the selected twins, then edit the seed records here."
        />
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Badge variant="secondary" className="h-5 rounded-md px-1.5 text-[11px]">
            {seedCount} records
          </Badge>
          <span>
            Saved scenarios are persisted as the sandbox&apos;s active seed overlay and snapshotted when a run starts.
          </span>
        </div>
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

function DetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-80" />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-[76px] w-full rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-40 w-full rounded-lg" />
    </div>
  );
}
