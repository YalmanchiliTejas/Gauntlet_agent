# Gauntlet UI Product Context

Use this document as the stable context for agents working on the Gauntlet UI.
Update it when the product flow, information architecture, or major UX decisions change.

## Product Intent

Gauntlet is a sandboxed evaluation and self-healing platform for AI agents.

The intended user flow:

1. User signs up or logs in.
2. User lands on the Sandboxes page.
3. User creates a sandbox or opens an existing sandbox.
4. Sandbox creation starts with:
   - GitHub repository connection.
   - Branch selection, defaulting to `main`.
   - Service twin selection.
5. Inside a sandbox, the user provides docs/context and generates automated workflows.
6. User runs their agent through those workflows.
7. Gauntlet captures failures from traces, egress, service twin state, and workflow verdicts.
8. Gauntlet proposes fixes and runs a self-healing loop against the agent/harness code.

The UI should make this feel lightweight, direct, and operational. Avoid heavy marketing pages, decorative hero sections, and visually noisy dashboard patterns.

## Current UI Architecture

The frontend lives in `web/`.

Stack:

- Next.js App Router.
- TypeScript.
- Tailwind CSS.
- shadcn/ui generated components.
- lucide-react icons.
- Mock fallback data for local demos when backend auth is not configured.

Important files:

- `web/src/app/layout.tsx`: root metadata, tooltip provider, toaster.
- `web/src/app/page.tsx`: redirects `/` to `/sandboxes`.
- `web/src/app/sandboxes/page.tsx`: Sandboxes dashboard.
- `web/src/components/app-shell.tsx`: collapsible left sidebar and app shell.
- `web/src/components/create-sandbox-sheet.tsx`: create sandbox sheet.
- `web/src/lib/sandbox-api.ts`: client-side API boundary for sandbox options, branches, list, and create.
- `web/src/lib/server/gauntlet-backend.ts`: server-side backend proxy helper.
- `web/src/app/api/sandboxes/*`: UI-facing Next API routes that call the Gauntlet backend when configured.
- `web/src/lib/mock-data.ts`: mock sandboxes, repos, branches, and twin options used as fallback data.
- `web/src/components/ui/*`: shadcn/ui source components.

## Design Direction

The product should feel calm, fast, and trustworthy.

Palette:

- Background: `#FAFAFA`
- Surface: `#FFFFFF`
- Sidebar: `#F6F7F9`
- Border: `#E5E7EB`
- Text primary: `#111827`
- Text muted: `#6B7280`
- Primary: `#2563EB`
- Success: green
- Warning: amber
- Failure: red

Layout principles:

- Use a light left sidebar.
- Sidebar is expandable/collapsible on desktop.
- Use icon-only collapsed state with titles/tooltips where appropriate.
- Keep dashboard layouts dense but not cramped.
- Use cards for repeated objects and framed tools, not as nested decorative wrappers.
- Keep primary actions obvious and sparse.
- Keep copy short and concrete.

## Primary Navigation

Current sidebar entries:

- Sandboxes
- Workflows
- Runs
- Fixes
- Settings

The first real product object is the sandbox. Workflows, runs, failures, and fixes should hang off a selected sandbox.

## Checkpoint Plan

### Checkpoint 1: App Shell + Sandboxes Home

Status: complete.

Scope:

- Create `web/`.
- Set up Next.js, Tailwind, shadcn/ui.
- Add light theme.
- Build collapsible left sidebar.
- Build `/sandboxes`.
- Add mock sandbox list.
- Add empty state branch.
- Add `Create sandbox` sheet trigger and basic mock controls.

### Checkpoint 2: Create Sandbox Flow

Status: complete.

Scope:

- Make sandbox creation interactive with local state.
- Repo selector.
- Branch selector defaulting to `main`.
- Twin multi-select/checklist.
- Loading, empty, and error states.
- Mock create behavior adds the sandbox to the list and closes the sheet.
- Define frontend types/API client boundaries for future backend integration.

### Checkpoint 3: Sandbox Detail + Workflow Entry Point

Status: not started.

Expected scope:

- Add `/sandboxes/[id]`.
- Header with repo, branch, selected twins, status.
- Tabs or sections:
  - Workflows
  - Runs
  - Failures
  - Fixes
- Add workflow generation entry point.
- Add docs/context upload placeholder.
- Add mock workflow list and run history.
- Prepare API call shapes for generate/list/run workflows.

## Backend Context To Keep In Mind

The current UI talks to the old FastAPI backend through local Next route handlers.
Configure the UI with:

- `GAUNTLET_API_URL`: backend base URL, for example `http://localhost:8000`.
- A user bearer token saved through `POST /api/session`, usually a Supabase JWT.
- `GAUNTLET_API_TOKEN`: optional local/dev fallback when no user session cookie exists.
- `NEXT_PUBLIC_GITHUB_APP_NAME`: GitHub App display name. Current default: `Gauntlet-Webhook`.
- `NEXT_PUBLIC_GITHUB_APP_SLUG`: GitHub App URL slug used for the install URL. Current default: `gauntlet-webhook`. It must be an installable app slug, not `GITHUB_APP_ID`.

If no bearer token is available, the UI intentionally falls back to mock data and marks the connection source as `mock`.

Relevant backend endpoints include:

- `POST /api/workflows/generate`
- `GET /api/workflows`
- `GET /api/workflows/{workflow_id}`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `POST /api/workflows/{workflow_id}/run`
- `POST /api/sandbox/fix`
- `GET /api/github/installations`
- `GET /api/github/repositories`
- `GET /api/github/repositories/{owner}/{repo}/branches`

The backend already has concepts for service twins under `twins/registry` and sandbox execution through `sandbox/orchestrator.py`, `gauntlet/runner.py`, and `gauntlet/app.py`.

The old backend now exposes GitHub App installation repository metadata from `gauntlet/server/routes/github.py`.
It mints installation tokens server-side via `gauntlet/server/github_app_client.py`; browser code must never receive those installation tokens.
The latest backend auth accepts either a CLI token or a Supabase JWT, so UI proxy routes should forward the user's bearer token rather than requiring a project-wide `GAUNTLET_API_TOKEN`.

Current UI auth/proxy routes:

- `POST /api/session`: verifies and stores the backend bearer token in httpOnly cookies.
- `DELETE /api/session`: clears those cookies.
- `GET /api/session/state`: checks whether the current browser has a usable backend session.
- `GET /github/callback`: accepts GitHub App `installation_id`, links it through `POST /api/github/installations`, and redirects back to `/sandboxes`.
- `POST /api/github/installations`: UI recovery route for manually linking an installation ID when GitHub leaves the user on `/settings/installations/{installation_id}` instead of redirecting to `/github/callback`.

GitHub App install behavior:

- If the GitHub App Setup URL is configured correctly, GitHub redirects to `/github/callback?installation_id=...&setup_action=...` after install/update.
- If the Setup URL is missing or not reachable, GitHub leaves the user on its installation settings page. In that case, the user can copy the numeric id from `github.com/settings/installations/{id}` and paste it into the create sandbox sheet's manual link field.
- The manual link field accepts either the full GitHub URL or just the numeric id, and the create sandbox sheet refreshes GitHub status every time it opens.

The UI-level sandbox list/create endpoints are still local MVP shims:

- `GET /api/sandboxes`
- `POST /api/sandboxes`

They return mock/local sandbox objects while the real persisted sandbox model is still being designed.

## UX Priorities

- Make the user’s next step obvious.
- Avoid making users understand internals like traces, egress logs, or harnesses before they need them.
- Keep sandbox creation to the minimum viable inputs:
  - repo
  - branch
  - twins
- Treat workflow generation as a sandbox-level action.
- Treat failures and fixes as the output of running workflows, not separate top-level setup tasks.

## Known Local Notes

- `npm run build` may need escalated execution in this environment because Next/Turbopack worker processes bind local ports.
- The project currently has unrelated untracked root docs/context files. Do not stage or delete them unless explicitly asked.
- The generated shadcn `Sheet` component was patched so it does not remain invisible due to stuck starting-state opacity in this environment.
