import { NextRequest, NextResponse } from "next/server";

import { backendFetch, BackendApiError } from "@/lib/server/gauntlet-backend";
import { repos, twinOptions } from "@/lib/mock-data";

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
  // Dev bypass: skip real backend, return mock repos as "connected" so the form renders.
  if (process.env.GAUNTLET_DEV_BYPASS === "true" && process.env.NODE_ENV !== "production") {
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
      twins: twinOptions,
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
