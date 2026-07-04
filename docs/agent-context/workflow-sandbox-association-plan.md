# Workflow Sandbox Association Plan

Use this document when working on workflow ownership, sandbox assignment, workflow generation UX, and duplicate prevention.

## Current State

The UI repo currently has sandbox-scoped workflow generation at:

- `POST /api/sandboxes/{id}/workflows`
- `GET /api/sandboxes/{id}/workflows`

Those routes write directly into `sandbox_workflows`, which means a workflow row belongs to exactly one sandbox. The top-level Workflows page reads all rows from the same table, but there is no first-class reusable workflow definition or many-to-many sandbox assignment model yet.

The backend repo at `/Users/aryanjain/projects/Gauntlet` has an older project/workflow model where workflows belong to a project. That model is useful context, but the current product UX is sandbox-first: users create a sandbox, add docs/context, generate workflows inside that sandbox, then run agents against that sandbox.

## Product Direction

Workflow generation should happen from inside a sandbox because generated workflows depend on:

- the repo and branch in that sandbox,
- selected twins/services,
- docs/context uploaded for that sandbox,
- seed data and simulated service state,
- the intended environment the agent will run inside.

At the same time, workflows should be reusable. A user should not regenerate a high-quality workflow just because they want to run it in another sandbox. The right model is:

- one canonical workflow definition,
- many sandbox assignments,
- sandbox-specific run history and seed/runtime state.

This is a many-to-many relationship between workflows and sandboxes.

## Target Data Model

Replace the current single-table mental model with two layers:

1. `workflows`
   - Canonical reusable workflow definition.
   - Owned by a user/workspace.
   - Stores name, description, task prompt, generated draft/config, services, quality metadata, source docs/context fingerprint, and generation parameters.

2. `sandbox_workflows`
   - Join table assigning a workflow to a sandbox.
   - Stores `sandbox_id`, `workflow_id`, assignment metadata, enabled/disabled state, and optional sandbox-specific overrides.
   - Should enforce uniqueness on `(sandbox_id, workflow_id)`.

Runs should reference both:

- `sandbox_id`, because execution always happens inside one sandbox.
- `workflow_id`, because the task definition is reusable.

For compatibility, keep API responses shaped like the current `Workflow` type, but add fields when useful:

- `workflowId` or `canonicalId`
- `sandboxIds`
- `assignedSandboxCount`
- `assignmentId`
- `sourceSandboxId`

## Implementation Order

### Part 1: Workflow Library And Sandbox Assignment

Goal: make workflow generation sandbox-first while allowing reuse across sandboxes.

Why first:

Duplicate prevention and focused generation both depend on knowing which workflows already exist in a sandbox. This should be built on the correct assignment model rather than patched into the current single-sandbox table.

Backend/API work:

- Add canonical `workflows` table if not already present in the active Supabase schema.
- Convert `sandbox_workflows` into a join/assignment table or introduce a new join table and migrate gradually.
- Add APIs:
  - `GET /api/workflows`: list all canonical workflows visible to the user, with assigned sandbox counts.
  - `GET /api/sandboxes/{id}/workflows`: list workflows assigned to a sandbox.
  - `POST /api/sandboxes/{id}/workflows/generate`: generate canonical workflows and assign them to this sandbox.
  - `POST /api/workflows/{workflowId}/sandboxes`: assign one workflow to one or more sandboxes.
  - `DELETE /api/sandboxes/{id}/workflows/{workflowId}`: unassign from this sandbox, not delete the canonical workflow.
  - `DELETE /api/workflows/{workflowId}`: delete canonical workflow only when user confirms, and cascade/unassign as intended.

UI work:

- Sandbox detail remains the main generation entry point.
- Top-level Workflows tab becomes a library view:
  - shows all workflows,
  - shows which sandbox(es) each workflow is assigned to,
  - lets users assign workflows to additional sandboxes,
  - lets users filter by sandbox, service, difficulty, generated/manual, and coverage area.
- Sandbox workflow list should show only assigned workflows.

UX rules:

- Users generate from a sandbox.
- Users reuse from the Workflows library.
- Deleting from a sandbox should say “Remove from sandbox,” not “Delete workflow.”
- Deleting from the library should be clearly destructive.

Acceptance criteria:

- A workflow generated in Sandbox A appears in Sandbox A.
- The same workflow can be assigned to Sandbox B without regeneration.
- Removing the workflow from Sandbox A does not delete it from Sandbox B or the library.
- Running a workflow always requires selecting or inferring a sandbox assignment.

### Part 2: Duplicate And Near-Duplicate Prevention

Goal: prevent workflow generation from adding workflows that are identical, near-identical, or coverage-equivalent to workflows already assigned to the target sandbox.

Why second:

The duplicate check must compare against the target sandbox’s assigned workflows, not merely all workflows in the workspace.

Generation request additions:

- Include existing assigned workflows in the generation context:
  - name,
  - description,
  - task prompt,
  - surface area,
  - target interfaces,
  - services/twins,
  - success conditions,
  - failure modes tested.

Deduplication layers:

1. Exact fingerprint
   - Normalize and hash important fields: task prompt, services, surface area, success conditions, target interfaces.
   - Reject exact duplicates before insert.

2. Heuristic similarity
   - Compare normalized title/task prompt token overlap.
   - Compare service set, target interfaces, and surface area.
   - Treat workflows as duplicates when they test the same operation with the same evidence and same service path.

3. LLM/council critique for borderline cases
   - Ask whether a candidate adds new coverage or just restates an existing workflow.
   - Require a clear novelty reason before accepting.

4. Post-generation coverage selection
   - Generate more candidates than requested.
   - Score candidates by quality, specificity, and incremental coverage.
   - Return the best non-overlapping subset.

UX behavior:

- If the user asks for 5 workflows but only 3 novel workflows are found, show:
  - “Generated 3 new workflows. 2 requested slots were skipped because similar workflows already exist.”
- Provide expandable “Skipped similar workflows” details with the matched existing workflow and reason.
- Allow an advanced override: “Generate variants anyway,” but default should protect quality.

Acceptance criteria:

- Re-running generation with the same docs and same focus does not create duplicate workflows in the same sandbox.
- Generating in another sandbox may reuse/assign existing workflows instead of creating new copies.
- Generated workflows include a `novelty_reason` or equivalent metadata explaining what new surface they cover.

### Part 3: Focused Workflow Generation

Goal: let users optionally tell Gauntlet what product area, risk, or behavior they want generation to focus on.

Why third:

Focused generation works best once workflows are sandbox-scoped and deduped. Otherwise users will ask for a focus area and still get repeated or misplaced workflows.

UX design:

- In the sandbox workflow generation modal, keep required inputs minimal:
  - docs/context,
  - number of workflows.
- Add an optional “Focus” field:
  - placeholder examples:
    - “Billing and failed payment recovery”
    - “OAuth setup and token refresh”
    - “Multi-step onboarding with Slack and Gmail”
    - “Edge cases around permissions and restricted accounts”
- Add optional quick chips:
  - “Happy paths”
  - “Edge cases”
  - “Multi-service workflows”
  - “Failure recovery”
  - “Security-sensitive flows”
  - “Regression coverage”

Harness/generator changes:

- Add `focus` to the workflow generation payload.
- Add `focus_mode` or derive intent:
  - `surface_area`
  - `risk_area`
  - `service`
  - `persona`
  - `failure_mode`
  - `integration`
- Update planner prompts to require:
  - workflows must satisfy the focus unless impossible,
  - each workflow must include `focus_alignment_reason`,
  - if docs do not support the focus, return a clear gap instead of inventing details.
- Update deterministic selectors to weight candidates matching focus higher.
- Include focus in deduplication so a generated workflow must be both novel and relevant.

UX behavior:

- If focus is provided and docs do not support it, show a useful empty state:
  - “We could not find enough documentation for billing recovery. Add docs or broaden the focus.”
- If some workflows partially match, show confidence and coverage notes.

Acceptance criteria:

- A user can generate workflows without focus exactly as before.
- A user can provide focus and receive workflows that are visibly aligned with it.
- Focused generation does not bypass duplicate prevention.
- Focus is stored as metadata for auditability and future regeneration.

## Recommended Build Sequence

1. Build workflow library and sandbox assignment first.
2. Add duplicate/near-duplicate prevention against assigned workflows.
3. Add focused generation with optional user guidance.

This order protects UX quality. Users first get a correct mental model: generate inside a sandbox, reuse through the library. Then generation becomes safer through dedupe. Finally, focused generation becomes high-value because it can target gaps instead of producing generic variants.

## Open Questions

- Should canonical workflows be workspace-owned or user-owned in the current auth model?
- Should workflow edits update the canonical workflow for all assigned sandboxes, or create a sandbox-specific override/version?
- Should assigning a workflow to another sandbox require compatible twins/services, or should incompatible assignments be blocked with a clear reason?
- Should duplicate prevention happen entirely in the Next API layer first, or should the Python generator also receive existing workflows and enforce novelty?

Default recommendation:

- Keep canonical workflows workspace/user-owned.
- Start without sandbox-specific overrides; add versioning later.
- Block assignment when required services are missing from the target sandbox, but offer to add compatible twins if possible.
- Enforce dedupe in both places: cheap deterministic checks in the API, deeper novelty scoring in the generator.

## Run Contract (run-contract-v1)

The workflow→sandbox association model is complete. The next layer connects assigned workflows to actual sandbox execution. Here is what was built and what remains.

### What Was Built (2026-07-03)

**Dispatch (Next.js → backend):**

- `POST /api/sandboxes/[id]/runs` now does the following after creating the Supabase run row:
  1. Fetches the user's GitHub installation ID from the backend.
  2. Resolves the HEAD SHA for the sandbox's repo+branch via the backend branches endpoint.
  3. Dispatches to `POST /api/sandbox/trigger` on the Fly backend with `{repo, sha, ref, installation_id, task_prompt, twins, workflow_id, egress_default}`.
  4. Passes the Supabase run ID as `workflow_id` so the status poller can look it up.
  5. On dispatch failure or missing infra, immediately marks the run as `error` with a clear message.

**Status polling (no callback URL required):**

- `GET /api/runs/[id]/status` (Next.js): reads Supabase; if run is still active, calls `GET /api/sandbox/run-status?workflow_id={id}` on the Fly backend. When the runner reports terminal state, writes result (verdict, error, finished_at) to Supabase and returns the updated run.
- Frontend `run-detail.tsx` polls this endpoint every 4 seconds while status is `queued` or `running`. Stops when status becomes terminal.

**Backend (Fly, `gauntlet-api.fly.dev`):**

- `POST /api/sandbox/trigger` extended: accepts `task_prompt`, `twins`, `modes`, `workflow_id`, `egress_default`, `callback_url`, `callback_secret` and passes them to the runner `Job`.
- `GET /api/sandbox/run-status?workflow_id={id}`: new endpoint; queries the runner store by `workflow_id`, returns `{found, status, verdict, error, exit_code, finished_at}`.
- `gauntlet/sandbox_runner/runner.py`: synced from Gauntlet_agent — now includes full `Job` fields, store-based run persistence, and `_fire_callback`.
- `gauntlet/sandbox_runner/store.py`: added `get_run_by_workflow_id` so the status endpoint can look up runs by Supabase run ID.
- Both machines redeployed and verified: `GET /api/sandbox/run-status?workflow_id=test-123` returns `{"found":false}` as expected.

**RunStatus type extended:** added `succeeded`, `canceled` to `RunStatus` in `sandbox-api.ts`. `run-status-badge.tsx` updated with styles for both.

### What Remains Before End-to-End Execution Works

1. **MicroVM/S3 infrastructure**: `MICROVM_S3_BUCKET`, AWS credentials, and Lambda MicroVM setup must be configured in the Fly backend env. Without this, dispatch queues the job but the runner falls back to Docker or errors.
2. **GitHub App**: `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY` must be set in the Fly backend for the runner to download source and create Check runs.
3. **Runner DB**: `DATABASE_URL` must be set in the Fly backend for run persistence (so the status poller can find runs). Without it, `get_run_by_workflow_id` always returns `not found` and runs stay `queued` in the UI.
4. **`egress-policy-v1`**: per-run egress routing policy (next priority feature).

### Open Design Questions

- Should `task_prompt` be stored on the sandbox_run row at dispatch time for auditing?
- Should the polling interval back off (e.g. 4s → 8s → 16s) for long-running jobs?
- Should the runs list page also poll, or only the run detail page?

## Implementation Status

Implemented in the current working tree:

- Added `migrations/0007_reusable_workflows.sql`.
  - Creates canonical `workflows`.
  - Adds `sandbox_workflows.workflow_id`.
  - Backfills existing sandbox workflow rows into canonical workflows.
  - Adds uniqueness on `(sandbox_id, workflow_id)`.
- Updated the Next API workflow layer.
  - `GET /api/workflows` prefers canonical workflows and includes sandbox assignment metadata.
  - `GET /api/sandboxes/{id}/workflows` lists assigned workflows.
  - `POST /api/sandboxes/{id}/workflows` now creates canonical workflows, assigns them to the sandbox, and filters duplicates before insert.
  - `POST /api/workflows/{id}/sandboxes` assigns a reusable workflow to one or more sandboxes.
  - `DELETE /api/sandboxes/{id}/workflows/{workflowId}` unassigns a workflow from one sandbox.
- Added deterministic duplicate prevention in `web/src/lib/server/workflow-dedupe.ts`.
  - Exact workflow fingerprints.
  - Heuristic near-duplicate checks using task tokens, services, and surface area.
- Added optional focused generation.
  - UI focus field and quick chips in the generation sheet.
  - Focus is sent through the Next generation route.
  - Focus metadata is stored in generated drafts.
- Updated the Workflows UI.
  - Top-level page behaves more like a reusable workflow library.
  - Workflows can be assigned to additional sandboxes.
  - Running uses a sandbox assignment id; editing/deleting uses the canonical workflow id.
- Updated the Sandbox detail UI.
  - Adds a sandbox-scoped Workflows section.
  - Generation can now happen directly inside the sandbox context.
- Updated the backend repo `/Users/aryanjain/projects/Gauntlet`.
  - `WorkflowGeneratePayload` accepts `focus` and `existing_workflows`.
  - The LLM planner prompt asks for `focus_alignment_reason` and `novelty_reason`.
  - Backend selection rejects candidates similar to existing workflows.

Verification run:

- `npm run lint` in `web`: passed.
- `npm run build` in `web`: passed.
- Python AST syntax check for modified workflow generator modules: passed.

Rollout notes:

- Apply `migrations/0007_reusable_workflows.sql` before relying on reusable workflow assignments in Supabase.
- The Next API has compatibility fallbacks for the old `sandbox_workflows` shape, but true many-to-many reuse requires the migration.
- Deploy the backend repo changes for the Python planner to receive and enforce `focus` and `existing_workflows`.
