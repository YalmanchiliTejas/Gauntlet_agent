"use client";

import * as React from "react";
import { Check, ExternalLink, GitBranch, GitFork, Loader2, Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  createSandbox,
  listBranches,
  listSandboxOptions,
  signInWithToken,
  type Branch,
  type SandboxOptionData,
} from "@/lib/sandbox-api";
import { getSupabaseClient } from "@/lib/supabase";
import type { Sandbox } from "@/lib/mock-data";
import { cn } from "@/lib/utils";

// GitHub mark SVG (lucide-react does not include the GitHub brand icon).
function GithubIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
      className={className}
    >
      <path d="M12 0C5.373 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.6.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c.955.004 1.917.129 2.817.376 2.29-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
    </svg>
  );
}

type CreateSandboxSheetProps = {
  optionData: SandboxOptionData | null;
  onOptionsLoaded: (data: SandboxOptionData) => void;
  onCreate: (sandbox: Sandbox) => void;
};

export function CreateSandboxSheet({
  optionData,
  onOptionsLoaded,
  onCreate,
}: CreateSandboxSheetProps) {
  const [open, setOpen] = React.useState(false);
  const [repo, setRepo] = React.useState("");
  const [branch, setBranch] = React.useState("main");
  const [branches, setBranches] = React.useState<Branch[]>([]);
  const [selectedTwins, setSelectedTwins] = React.useState<string[]>([]);
  const [repoQuery, setRepoQuery] = React.useState("");
  const [loadingOptions, setLoadingOptions] = React.useState(false);
  const [loadingBranches, setLoadingBranches] = React.useState(false);
  const [creating, setCreating] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Derived connection state.
  const isConnected =
    optionData?.connection.source === "github_app" && optionData.connection.connected;
  // Show the connect card whenever optionData has loaded but GitHub is not connected.
  const needsGitHubConnect = optionData !== null && !isConnected;
  const installUrl = optionData?.connection.installUrl ?? null;

  async function loadOptions({ force = false }: { force?: boolean } = {}) {
    if ((!force && optionData) || loadingOptions) {
      return;
    }
    setLoadingOptions(true);
    setError(null);
    try {
      const data = await listSandboxOptions();
      onOptionsLoaded(data);
      initializeFromOptions(data);
      const firstRepo = data.repositories[0];
      if (firstRepo) {
        await loadBranchesForRepo(firstRepo.fullName, data);
      }
    } catch {
      setError("Could not load repositories.");
    } finally {
      setLoadingOptions(false);
    }
  }

  function initializeFromOptions(data: SandboxOptionData) {
    const firstRepo = data.repositories[0];
    setRepo((current) => current || firstRepo?.fullName || "");
    setBranch((current) => current || firstRepo?.defaultBranch || "main");
    setSelectedTwins((current) =>
      current.length > 0 ? current : data.twins.slice(0, 2).map((twin) => twin.id),
    );
  }

  async function loadBranchesForRepo(nextRepo: string, data = optionData) {
    if (!nextRepo) return;
    setLoadingBranches(true);
    setError(null);
    try {
      const items = await listBranches(nextRepo, data?.connection.installationId);
      setBranches(items);
      const defaultBranch =
        data?.repositories.find((item) => item.fullName === nextRepo)?.defaultBranch ?? "main";
      const nextBranch = items.some((item) => item.name === defaultBranch)
        ? defaultBranch
        : items[0]?.name ?? "main";
      setBranch((current) => (items.some((item) => item.name === current) ? current : nextBranch));
    } catch {
      setError("Could not load branches for this repository.");
    } finally {
      setLoadingBranches(false);
    }
  }

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) return;
    if (optionData) {
      initializeFromOptions(optionData);
      const nextRepo = repo || optionData.repositories[0]?.fullName || "";
      void loadBranchesForRepo(nextRepo, optionData);
    }
    void loadOptions({ force: true });
  }

  const repositories = optionData?.repositories ?? [];
  const twins = optionData?.twins ?? [];
  const filteredRepos = repositories.filter((item) =>
    item.fullName.toLowerCase().includes(repoQuery.toLowerCase()),
  );
  const selectedRepo = repositories.find((item) => item.fullName === repo);

  function toggleTwin(id: string, checked: boolean) {
    setSelectedTwins((current) =>
      checked ? [...new Set([...current, id])] : current.filter((item) => item !== id),
    );
  }

  async function submit() {
    if (!repo || !branch) {
      setError("Select a repository and branch before creating a sandbox.");
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const sandbox = await createSandbox({ repo, branch, twinIds: selectedTwins });
      onCreate(sandbox);
      setOpen(false);
      toast.success("Sandbox created", {
        description: `${sandbox.repo}@${sandbox.branch} is ready for workflow generation.`,
      });
    } catch {
      setError("Could not create sandbox.");
    } finally {
      setCreating(false);
    }
  }

  // Decide what to show in the content area.
  let contentBody: React.ReactNode;

  if (loadingOptions) {
    contentBody = <CreateSandboxSkeleton />;
  } else if (needsGitHubConnect) {
    contentBody = (
      <GitHubConnectCard
        connection={optionData!.connection}
        onSignedIn={() => void loadOptions({ force: true })}
      />
    );
  } else {
    // Connected (real repos) or mock fallback (demo repos).
    contentBody = (
      <div className="space-y-5">
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900">
            {error}
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="repo">GitHub repository</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="repo-search"
              className="pl-9"
              placeholder="Search repositories"
              aria-label="Search repositories"
              value={repoQuery}
              onChange={(event) => setRepoQuery(event.target.value)}
            />
          </div>
          <Select
            value={repo}
            onValueChange={(value) => {
              const nextRepo = String(value);
              setRepo(nextRepo);
              const nextDefault =
                repositories.find((item) => item.fullName === nextRepo)?.defaultBranch ?? "main";
              setBranch(nextDefault);
              void loadBranchesForRepo(nextRepo);
            }}
          >
            <SelectTrigger id="repo" className="h-10 w-full">
              <GitFork className="size-4 text-muted-foreground" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="start">
              {filteredRepos.length > 0 ? (
                filteredRepos.map((item) => (
                  <SelectItem key={item.id} value={item.fullName}>
                    {item.fullName}
                  </SelectItem>
                ))
              ) : (
                <div className="px-2 py-3 text-sm text-muted-foreground">
                  No repositories match this search.
                </div>
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="branch">Branch</Label>
          <Select value={branch} onValueChange={(value) => setBranch(String(value))}>
            <SelectTrigger id="branch" className="h-10 w-full">
              <GitBranch className="size-4 text-muted-foreground" />
              <SelectValue />
              {loadingBranches && <Loader2 className="ml-auto size-4 animate-spin" />}
            </SelectTrigger>
            <SelectContent align="start">
              {branches.map((item) => (
                <SelectItem key={item.name} value={item.name}>
                  {item.name}
                  {item.protected ? " protected" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-3">
          <div>
            <Label>Twins</Label>
            <p className="mt-1 text-sm text-muted-foreground">
              Select cloned services available inside the sandbox.
            </p>
          </div>
          <div className="grid gap-2">
            {twins.map((twin) => {
              const checked = selectedTwins.includes(twin.id);
              return (
                <label
                  key={twin.id}
                  className={cn(
                    "flex items-start gap-3 rounded-lg border bg-card p-3 transition-colors",
                    checked ? "border-primary/40 bg-accent/60" : "hover:bg-muted/70",
                  )}
                >
                  <Checkbox
                    checked={checked}
                    onCheckedChange={(next) => toggleTwin(twin.id, next)}
                    className="mt-0.5"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className={cn("size-2 rounded-full", twin.tone)} />
                      <span className="text-sm font-medium text-foreground">{twin.name}</span>
                      <Badge variant="secondary" className="h-5 rounded-md px-1.5 text-[11px]">
                        {twin.version}
                      </Badge>
                    </span>
                    <span className="mt-1 block text-sm text-muted-foreground">
                      {twin.description}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        </div>

        <div className="rounded-lg border bg-muted/50 p-3">
          <div className="flex items-center gap-2 text-sm font-medium">
            <Check className="size-4 text-primary" />
            Sandbox summary
          </div>
          <div className="mt-2 text-sm text-muted-foreground">
            {repo || "No repository selected"} on{" "}
            <span className="font-medium text-foreground">{branch}</span> with{" "}
            {selectedTwins.length} selected twin
            {selectedTwins.length === 1 ? "" : "s"}.
            {selectedRepo && selectedRepo.defaultBranch === branch && (
              <span className="ml-1 text-foreground">Default branch.</span>
            )}
          </div>
        </div>
      </div>
    );
  }

  const canCreate = isConnected && !!repo && !!branch;
  const needsSignIn = needsGitHubConnect && optionData?.connection.reason === "unauthenticated";
  const needsGitHubInstall = needsGitHubConnect && !needsSignIn;

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetTrigger render={<Button size="lg" />}>
        <Plus />
        Create sandbox
      </SheetTrigger>
      <SheetContent className="w-full border-l bg-card p-0 sm:max-w-none md:!w-[520px]">
        <SheetHeader className="border-b px-6 py-5">
          <SheetTitle>Create sandbox</SheetTitle>
          <SheetDescription>
            Choose the repository, branch, and service twins for this environment.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5">{contentBody}</div>

        <SheetFooter className="border-t px-6 py-4">
          <Button
            type="button"
            onClick={needsGitHubInstall ? undefined : needsSignIn ? undefined : submit}
            className="w-full"
            disabled={needsSignIn || creating || loadingOptions || loadingBranches || !canCreate}
            render={needsGitHubInstall && installUrl ? <a href={installUrl} /> : undefined}
          >
            {creating && <Loader2 className="animate-spin" />}
            {needsSignIn ? (
              "Sign in above to continue"
            ) : needsGitHubInstall ? (
              <>
                <GithubIcon className="size-4" />
                Connect to GitHub
              </>
            ) : creating ? (
              "Creating…"
            ) : (
              "Create sandbox"
            )}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

function GitHubConnectCard({
  connection,
  onSignedIn,
}: {
  connection: SandboxOptionData["connection"];
  onSignedIn: () => void;
}) {
  const needsSignIn = connection.reason === "unauthenticated";

  if (needsSignIn) {
    return <SignInCard onSignedIn={onSignedIn} />;
  }

  const installUrl = connection.installUrl ?? null;

  return (
    <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-5 text-center">
      <div className="flex size-14 items-center justify-center rounded-2xl border bg-card shadow-sm">
        <GithubIcon className="size-7 text-foreground" />
      </div>
      <div className="max-w-[260px]">
        <p className="text-sm font-semibold text-foreground">Connect to GitHub</p>
        <p className="mt-1.5 text-sm text-muted-foreground">
          Install the Gauntlet GitHub App to load your repositories and branches.
        </p>
      </div>
      {installUrl ? (
        <Button render={<a href={installUrl} />} className="gap-2">
          <GithubIcon className="size-4" />
          Connect to GitHub
          <ExternalLink className="size-3.5 opacity-70" />
        </Button>
      ) : (
        <p className="text-xs text-muted-foreground">
          Set <code className="font-mono">NEXT_PUBLIC_GITHUB_APP_SLUG</code> to enable.
        </p>
      )}
    </div>
  );
}

// Google "G" logo — not in lucide-react.
function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
    </svg>
  );
}

function SignInCard({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [signingIn, setSigningIn] = React.useState(false);
  const [googleLoading, setGoogleLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const supabase = React.useMemo(() => getSupabaseClient(), []);

  async function handleEmailSignIn(e: React.FormEvent) {
    e.preventDefault();
    if (!email || !password) return;
    setSigningIn(true);
    setError(null);
    try {
      if (!supabase) throw new Error("Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.");
      const { data, error: sbError } = await supabase.auth.signInWithPassword({ email, password });
      if (sbError || !data.session?.access_token) throw new Error(sbError?.message ?? "Sign-in failed.");
      await signInWithToken(data.session.access_token);
      onSignedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setSigningIn(false);
    }
  }

  async function handleGoogleSignIn() {
    setGoogleLoading(true);
    setError(null);
    try {
      if (!supabase) throw new Error("Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.");
      const { error: sbError } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}/auth/callback` },
      });
      if (sbError) throw new Error(sbError.message);
      // Browser will navigate away to Google — loading state stays until redirect.
    } catch (err) {
      setError(err instanceof Error ? err.message : "Google sign-in failed.");
      setGoogleLoading(false);
    }
  }

  const busy = signingIn || googleLoading;

  return (
    <div className="flex h-full min-h-[340px] flex-col items-center justify-center gap-5">
      <div className="w-full max-w-[280px] text-center">
        <p className="text-sm font-semibold text-foreground">Sign in to Gauntlet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Sign in to connect GitHub and load your repositories.
        </p>
      </div>

      <div className="w-full max-w-[280px] space-y-3">
        {/* Google OAuth */}
        <Button
          type="button"
          variant="outline"
          className="w-full gap-2"
          onClick={() => void handleGoogleSignIn()}
          disabled={busy}
        >
          {googleLoading ? <Loader2 className="size-4 animate-spin" /> : <GoogleIcon className="size-4" />}
          Continue with Google
        </Button>

        {/* Divider */}
        <div className="flex items-center gap-3">
          <div className="h-px flex-1 bg-border" />
          <span className="text-xs text-muted-foreground">or</span>
          <div className="h-px flex-1 bg-border" />
        </div>

        {/* Email + password */}
        <form onSubmit={(e) => void handleEmailSignIn(e)} className="space-y-2">
          <Input
            type="email"
            placeholder="Email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
          />
          <Input
            type="password"
            placeholder="Password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
          <Button type="submit" className="w-full" disabled={busy || !email || !password}>
            {signingIn ? <Loader2 className="size-4 animate-spin" /> : null}
            Sign in
          </Button>
        </form>

        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>
    </div>
  );
}


function CreateSandboxSkeleton() {
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-10 w-full" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-4 w-16" />
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-20 w-full rounded-lg" />
        ))}
      </div>
    </div>
  );
}
