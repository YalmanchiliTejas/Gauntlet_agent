# Gauntlet UI Progress Log

Update this document after every meaningful UI change set. Keep entries factual and action-oriented so another agent can resume without reconstructing context from chat history.

## 2026-07-02: Checkpoint 1 Complete

Goal completed:

> Complete Checkpoint 1: scaffold the frontend app shell with shadcn-style light UI, collapsible sidebar, and `/sandboxes` page with mock sandbox list, empty state, and create sandbox sheet trigger.

### Files Added

- `web/package.json`
- `web/package-lock.json`
- `web/components.json`
- `web/next.config.ts`
- `web/postcss.config.mjs`
- `web/eslint.config.mjs`
- `web/tsconfig.json`
- `web/src/app/layout.tsx`
- `web/src/app/page.tsx`
- `web/src/app/sandboxes/page.tsx`
- `web/src/app/globals.css`
- `web/src/components/app-shell.tsx`
- `web/src/components/create-sandbox-sheet.tsx`
- `web/src/components/ui/*`
- `web/src/lib/mock-data.ts`
- `web/src/lib/utils.ts`

### Files Modified

- `.gitignore`
  - Added `.gstack/` so local gstack runtime state does not pollute git status.

### Implemented

- New Next.js frontend in `web/`.
- shadcn/ui initialized.
- Light Gauntlet theme tokens.
- Root metadata for Gauntlet.
- `/` redirects to `/sandboxes`.
- `/sandboxes` page with:
  - Header and primary create action.
  - Metrics cards.
  - Mock sandbox list.
  - Responsive mobile layout.
  - Empty state branch.
- Collapsible desktop left sidebar with:
  - Sandboxes
  - Workflows
  - Runs
  - Fixes
  - Settings
- Create sandbox sheet with mock controls:
  - GitHub repository selector.
  - Branch selector defaulting to `main`.
  - Twin checklist.
  - Sandbox summary.
  - Toast feedback on create.

### Fixes Made During Verification

- Removed `next/font/google` usage so builds do not depend on fetching Google Fonts.
- Replaced unavailable lucide brand icon imports with available generic icons.
- Fixed sidebar collapsed state initialization to satisfy React lint rules.
- Patched generated `Sheet` component:
  - Removed stuck `data-starting-style:opacity-0` behavior that made the sheet invisible in browser screenshots.
  - Removed default `sm:max-w-sm` sheet width cap so callers can control panel width.
- Set create sandbox sheet to `520px` on desktop and full width on small screens.

### Verification

Commands run:

```bash
cd web
npm run lint
npm run build
```

Results:

- `npm run lint`: passed.
- `npm run build`: passed.

Browser verification:

- Started dev server with `npm run dev -- --port 3000`.
- Opened `http://localhost:3000/sandboxes`.
- Confirmed page rendered.
- Confirmed create sandbox sheet opens.
- Confirmed sheet is visible and 520px wide on desktop.
- Confirmed no browser console errors.
- Checked mobile viewport `390x844`; layout is usable.

Screenshots:

- Dashboard/mobile screenshot: `/tmp/gauntlet-sandboxes-mobile.png`
- Final create sandbox sheet screenshot: `/tmp/gauntlet-checkpoint1-final.png`

### Current State

The UI is currently mock-data only. It does not call backend APIs yet.

The dev server was stopped after verification.

Known git state after this checkpoint:

- `web/` is untracked until staged.
- `.gitignore` is modified.
- Existing unrelated root context/docs remain untracked and untouched.

### Next Recommended Work

Checkpoint 2 should make create sandbox behavior interactive and prepare backend wiring.

Recommended scope:

1. Move sandbox list into client state or a small local store.
2. Make `CreateSandboxSheet` call an `onCreateSandbox` callback.
3. When the user creates a sandbox, add it to the visible list.
4. Add loading, empty, and error states.
5. Define API client types for:
   - repositories
   - branches
   - twins
   - sandboxes
6. Decide whether sandbox persistence is implemented in this repo now or mocked until backend endpoints exist.

Do not start workflow generation UI until sandbox creation and sandbox detail routing are clear.

## 2026-07-02: Checkpoint 2 Complete

Goal completed:

> Complete Checkpoint 2: make the create sandbox flow interactive with local state, loading/empty/error states, frontend API boundaries, and determine how much GitHub connection wiring can be supported by existing backend code before implementation.

### Files Added

- `web/src/lib/sandbox-api.ts`
  - Frontend API boundary for sandbox UI data.
  - Mock-backed functions:
    - `listSandboxOptions`
    - `listSandboxes`
    - `listBranches`
    - `createSandbox`
  - Types:
    - `Repository`
    - `Branch`
    - `GitHubConnection`
    - `CreateSandboxInput`
    - `SandboxOptionData`
  - Documents required future backend endpoints in `requiredGithubUiEndpoints`.
- `web/src/components/sandboxes-workspace.tsx`
  - Client-side sandboxes workspace with state, loading, error, empty, and create handling.

### Files Modified

- `web/src/app/sandboxes/page.tsx`
  - Now renders `SandboxesWorkspace`.
- `web/src/components/create-sandbox-sheet.tsx`
  - Converted from static mock sheet to interactive create flow.
  - Loads repositories/twins through `sandbox-api.ts`.
  - Loads branches per selected repository.
  - Creates sandbox through `createSandbox`.
  - Closes on success.
  - Calls parent `onCreate` so the new sandbox appears in the list.
  - Shows loading, empty search, and error states.
- `web/src/lib/mock-data.ts`
  - Renamed `sandboxes` to `initialSandboxes`.
  - Replaced string repo list with typed repository objects.
  - Added repo-specific branch data.
- `docs/agent-context/ui-product-context.md`
  - Marked Checkpoint 2 complete.
  - Added GitHub/backend endpoint gap and expected API shape.

### Implemented

- Sandboxes load asynchronously through a frontend API boundary.
- Create sandbox sheet loads options asynchronously.
- Branch selector updates based on selected repository.
- Create button shows loading state.
- Successful create:
  - Creates a sandbox object.
  - Adds it to the top of the sandbox list.
  - Closes the sheet.
  - Shows a success toast.
- Dashboard stats update from local state after create.
- Repository search empty state works.
- Error states exist for:
  - sandbox list load
  - option load
  - branch load
  - create failure
- A visible amber notice explains that GitHub UI endpoints are not wired yet and that mock data is being used behind the API boundary.

### GitHub Wiring Findings

Existing backend support:

- `gauntlet/github.py` supports runner-oriented GitHub App operations:
  - mint installation token
  - download source
  - create branch
  - write file
  - open pull request
  - create/complete check run
- `gauntlet/app.py` supports GitHub webhooks and run triggering.
- `gauntlet/store.py` persists users, runs, and workflows.

Missing backend UI support:

- No endpoint found for listing GitHub installations.
- No endpoint found for listing repositories available to the user/install.
- No endpoint found for listing branches for a repository.
- No sandbox persistence table or `GET/POST /sandboxes` endpoint found.

Conclusion:

- Full GitHub connection is **not** wired in Checkpoint 2.
- The UI is prepared for it through `web/src/lib/sandbox-api.ts`.
- Real wiring should happen by replacing mock functions after backend endpoints are added.

Expected backend endpoints:

```text
GET /github/installations
GET /github/repositories
GET /github/repositories/{owner}/{repo}/branches
GET /sandboxes
POST /sandboxes
```

### Verification

Commands run:

```bash
cd web
npm run lint
npm run build
```

Results:

- `npm run lint`: passed.
- `npm run build`: passed.

Browser verification:

- Started dev server with `npm run dev -- --port 3000`.
- Opened `http://localhost:3000/sandboxes`.
- Confirmed initial sandboxes load.
- Confirmed no console errors.
- Opened create sandbox sheet.
- Clicked create.
- Confirmed sheet closed.
- Confirmed sandbox row count became 4.
- Confirmed new sandbox appeared at top with `Never run`.
- Confirmed dashboard stats updated to `Sandboxes 4`, `Ready 2`, `Running 1`.
- Confirmed repository search empty state with `zzz`.

Screenshot:

- `/tmp/gauntlet-checkpoint2-created.png`

### Current State

The UI is still mock-backed, but the mock is now behind an API boundary.

The dev server was stopped after verification.

Known git state after this checkpoint:

- `web/` is untracked until staged.
- `.gitignore` is modified with `.gstack/`.
- `docs/agent-context/ui-product-context.md` and `docs/agent-context/ui-progress-log.md` are untracked unless staged.
- Existing unrelated root context/docs remain untracked and untouched.

### Next Recommended Work

Checkpoint 3 should create the sandbox detail workspace.

Recommended scope:

1. Add `/sandboxes/[id]`.
2. Use selected sandbox data from mock/API boundary.
3. Add header showing repo, branch, twins, and status.
4. Add tabs/sections:
   - Workflows
   - Runs
   - Failures
   - Fixes
5. Add a clear workflow generation entry point.
6. Add docs/context upload placeholder UI.
7. Prepare API client shapes for:
   - generate workflows
   - list workflows for sandbox
   - run workflow in sandbox
   - list runs for sandbox

## GitHub Backend Hookup

### What Changed

- Inspected the old backend in `/Users/aryanjain/projects/Gauntlet`.
- Confirmed it already had GitHub App installation persistence through:
  - `POST /api/github/installations`
  - `GET /api/github/installations`
  - `DELETE /api/github/installations/{installation_id}`
- Added old-backend read-only GitHub App metadata support:
  - `gauntlet/server/github_app_client.py`
  - `GET /api/github/repositories`
  - `GET /api/github/repositories/{owner}/{repo}/branches`
- Added `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY`/`GITHUB_APP_PRIVATE_KEY_FILE` to old backend settings.
- Added current-repo Next API proxy routes:
  - `GET /api/sandboxes/options`
  - `GET /api/sandboxes/branches?repo=owner/name`
  - `GET /api/sandboxes`
  - `POST /api/sandboxes`
- Updated `web/src/lib/sandbox-api.ts` so the create sandbox sheet uses those routes instead of direct mock functions.
- Added `GAUNTLET_API_URL` and `GAUNTLET_API_TOKEN` to `.env.example`.

### Current Behavior

- With `GAUNTLET_API_URL` and a bearer token from `POST /api/session`, the create sandbox sheet loads linked GitHub installations and real repositories/branches from the old backend.
- `GAUNTLET_API_TOKEN` still works as a local/dev fallback when no browser session cookie exists.
- Without a bearer token, the UI falls back to mock repo/branch data and shows the mock warning banner.
- Sandbox persistence is still an MVP shim in the current Next app, not a real old-backend model yet.

### Verification

- Old backend changed files passed AST syntax parsing without bytecode writes:

```bash
python -c "import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(), filename=p) for p in ['gauntlet/server/routes/github.py','gauntlet/server/github_app_client.py','gauntlet/server/config.py']]; print('syntax ok')"
```

## GitHub Integration Auth Update

### What Changed

- Re-read latest backend commits:
  - `d7524c0` added GitHub installation persistence endpoints.
  - `96d709b` made backend auth accept Supabase JWTs, removing the need for users to mint a separate API token.
- Updated current UI backend proxy to use this order:
  - incoming `Authorization: Bearer ...` header
  - httpOnly `gauntlet_api_token` cookie
  - optional `GAUNTLET_API_TOKEN` local/dev fallback
- Added session routes in current UI:
  - `POST /api/session`
  - `DELETE /api/session`
  - `GET /api/session/state`
- Added `GET /github/callback` to link GitHub App installations through the backend.
- Added `POST /api/github/installations` as a manual recovery path for GitHub installs that land on GitHub's settings page instead of redirecting through the setup callback.
- Improved that recovery path so the create sandbox sheet refreshes GitHub status on every open and accepts either the full GitHub installation URL or the numeric installation id.
- Added GitHub App install URL support in sandbox options and create sandbox sheet.
- Set frontend GitHub App defaults to display name `Gauntlet-Webhook` and install slug `gauntlet-webhook`.

### Verification

- `npm run lint`: passed.
- `npm run build`: passed.
- Old backend GitHub/config files pass AST syntax parsing.
- Dev server starts on an alternate port, but local `curl` cannot connect to the reported port in this sandbox. This appears to be an environment networking limitation seen in prior checks, not a compile/runtime route issue.

## Workflow Reuse And Focused Generation

### What Changed

- Added `docs/agent-context/workflow-sandbox-association-plan.md`.
- Added `migrations/0007_reusable_workflows.sql`.
  - Canonical `workflows` table.
  - `sandbox_workflows.workflow_id` assignment link.
  - Backfill from existing sandbox workflow rows.
  - Unique `(sandbox_id, workflow_id)` assignment index.
- Updated workflow API routes:
  - `GET /api/workflows` prefers canonical workflows with assignment metadata.
  - `GET /api/sandboxes/{id}/workflows` lists assigned workflows for one sandbox.
  - `POST /api/sandboxes/{id}/workflows` creates canonical workflows, assigns them to the sandbox, and skips duplicate/near-duplicate candidates.
  - `POST /api/workflows/{id}/sandboxes` assigns a reusable workflow to one or more sandboxes.
  - `DELETE /api/sandboxes/{id}/workflows/{workflowId}` removes a workflow from one sandbox without deleting the canonical workflow.
- Added `web/src/lib/server/workflow-dedupe.ts`.
  - Fingerprint-based duplicate detection.
  - Heuristic near-duplicate detection.
- Updated `web/src/components/workflows-workspace.tsx`.
  - Workflows page behaves as a reusable workflow library.
  - Workflows can be assigned to additional sandboxes.
  - Optional focus input and focus quick chips added to generation.
- Updated `web/src/components/sandbox-detail.tsx`.
  - Sandbox detail now has a Workflows section.
  - Users can generate workflows from inside the sandbox context.

### Backend Repo Changes

In `/Users/aryanjain/projects/Gauntlet`:

- `gauntlet/workflows/api_models.py`
- `gauntlet/workflows/schema.py`
- `gauntlet/workflows/generate.py`
- `gauntlet/workflows/llm_planner.py`
- `gauntlet/workflows/select.py`

The backend generator now accepts `focus` and `existing_workflows`, asks the LLM planner for focus alignment and novelty reasons, and rejects candidates similar to existing workflows before final selection.

### Verification

- `npm run lint`: passed.
- `npm run build`: passed.
- Python AST syntax check on modified backend workflow modules: passed.

### Rollout Notes

- Apply `migrations/0007_reusable_workflows.sql` before expecting true many-to-many workflow reuse.
- The Next API includes legacy fallbacks for the old `sandbox_workflows` table shape, but reusable assignment requires the migration.
- Deploy the backend repo for LLM-level focus and novelty enforcement.
