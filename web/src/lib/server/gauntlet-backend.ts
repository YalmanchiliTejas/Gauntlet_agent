import { cookies } from "next/headers";
import type { NextRequest } from "next/server";

export const DEFAULT_GAUNTLET_API_URL = "https://gauntlet-api.fly.dev";

export const API_URL_COOKIE = "gauntlet_api_url";
export const API_TOKEN_COOKIE = "gauntlet_api_token";

export class BackendApiError extends Error {
  status: number;

  constructor(message: string, status = 500) {
    super(message);
    this.name = "BackendApiError";
    this.status = status;
  }
}

function bearerFromRequest(request?: NextRequest) {
  const authorization = request?.headers.get("authorization") || "";
  if (!authorization.toLowerCase().startsWith("bearer ")) {
    return "";
  }
  return authorization.slice("bearer ".length).trim();
}

export async function getBackendSession(request?: NextRequest) {
  const store = await cookies();
  const apiUrl =
    request?.headers.get("x-gauntlet-api-url") ||
    store.get(API_URL_COOKIE)?.value ||
    process.env.GAUNTLET_API_URL ||
    DEFAULT_GAUNTLET_API_URL;
  const accessToken =
    bearerFromRequest(request) ||
    store.get(API_TOKEN_COOKIE)?.value ||
    process.env.GAUNTLET_API_TOKEN ||
    "";

  return {
    apiUrl: apiUrl.replace(/\/$/, ""),
    accessToken,
  };
}

export async function backendFetch<T>(
  path: string,
  init?: RequestInit,
  request?: NextRequest,
): Promise<T> {
  const session = await getBackendSession(request);
  if (!session.accessToken) {
    throw new BackendApiError("No backend bearer token is available.", 401);
  }

  let response: Response;
  try {
    response = await fetch(`${session.apiUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.accessToken}`,
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new BackendApiError(`Backend fetch failed: ${message}`, 502);
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.error || detail;
    } catch {
      // Keep status text if the backend did not return JSON.
    }
    throw new BackendApiError(detail, response.status);
  }

  return (await response.json()) as T;
}
