import { NextRequest, NextResponse } from "next/server";

import { backendFetch, BackendApiError } from "@/lib/server/gauntlet-backend";
import { getServerSupabase, isDevBypass } from "@/lib/server/supabase";
import { repos, twinOptions, type TwinOption } from "@/lib/mock-data";

// Overlay the live twin catalog (shipped services + on-disk versions) onto the
// static descriptions/tones. Falls back to twinOptions if the backend is down.
async function resolveTwins(request: NextRequest): Promise<TwinOption[]> {
  try {
    const { twins } = await backendFetch<{ twins: { id: string; versions: string[] }[] }>(
      "/twins",
      undefined,
      request,
    );
    return twins.map(({ id, versions }) => {
      const meta = twinOptions.find((twin) => twin.id === id);
      return {
        id,
        name: meta?.name ?? id,
        versions,
        description: meta?.description ?? "",
        tone: meta?.tone ?? "bg-neutral-500",
      };
    });
  } catch {
    return twinOptions;
  }
}

type BackendInstallation = {
  installation_id: number;
  account_login?: string | null;
};

type BackendRepository = {
  id: string | number;
  full_name: string;
  default_branch?: string | null;
};

const DEFAULT_GITHUB_APP_NAME = "Gauntlet-Webhook";
const DEFAULT_GITHUB_APP_SLUG = "gauntlet-webhook";

function githubAppInstallUrl() {
  const slug =
    process.env.NEXT_PUBLIC_GITHUB_APP_SLUG ||
    process.env.GITHUB_APP_SLUG ||
    DEFAULT_GITHUB_APP_SLUG;
  return slug ? `https://github.com/apps/${slug}/installations/new` : null;
}

function githubAppName() {
  return process.env.NEXT_PUBLIC_GITHUB_APP_NAME || DEFAULT_GITHUB_APP_NAME;
}

export async function GET(request: NextRequest) {
  // Dev bypass skips the GitHub backend, but still requires a real Supabase
  // session when Supabase is configured so creates are actually persisted.
  if (isDevBypass()) {
    const supabaseConfigured =
      Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL) &&
      Boolean(process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
    const supabase = await getServerSupabase();

    if (supabaseConfigured && !supabase) {
      return NextResponse.json({
        connection: {
          connected: false,
          installationId: null,
          source: "mock",
          reason: "unauthenticated",
          message: "Sign in to store sandboxes in Supabase.",
          installUrl: githubAppInstallUrl(),
        },
        repositories: [],
        twins: twinOptions,
      });
    }

    return NextResponse.json({
      connection: {
        connected: true,
        installationId: 99999,
        source: "github_app",
        message: "Dev bypass — mock repositories active.",
        installUrl: githubAppInstallUrl(),
      },
      repositories: repos,
      twins: twinOptions,
    });
  }

  try {
    const installationPayload = await backendFetch<{ installations: BackendInstallation[] }>(
      "/api/github/installations",
      undefined,
      request,
    );
    const installation = installationPayload.installations[0];

    if (!installation) {
      return NextResponse.json({
        connection: {
          connected: false,
          installationId: null,
          source: "github_app",
          message: `Install ${githubAppName()} to select repositories.`,
          installUrl: githubAppInstallUrl(),
        },
        repositories: [],
        twins: twinOptions,
      });
    }

    const repoPayload = await backendFetch<{ repositories: BackendRepository[] }>(
      `/api/github/repositories?installation_id=${installation.installation_id}`,
      undefined,
      request,
    );

    return NextResponse.json({
      connection: {
        connected: true,
        installationId: installation.installation_id,
        source: "github_app",
        message: installation.account_login
          ? `Connected to ${installation.account_login}.`
          : `${githubAppName()} installation connected.`,
        installUrl: githubAppInstallUrl(),
      },
      repositories: repoPayload.repositories.map((repo) => ({
        id: String(repo.id),
        fullName: repo.full_name,
        defaultBranch: repo.default_branch || "main",
      })),
      twins: await resolveTwins(request),
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "Backend unavailable.";
    const status = error instanceof BackendApiError ? error.status : 500;

    return NextResponse.json({
      connection: {
        connected: false,
        installationId: null,
        source: "mock",
        reason: status === 401 ? "unauthenticated" : "backend_unavailable",
        message:
          status === 401
            ? "Sign in to load your GitHub repositories."
            : `Backend unavailable: ${detail}`,
        installUrl: githubAppInstallUrl(),
      },
      repositories: repos,
      twins: twinOptions,
    });
  }
}
