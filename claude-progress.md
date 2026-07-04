# Gauntlet Progress Log

## Current Verified State

- Repository root directory: `/Users/aryanjain/projects/Gauntlet_agent`
- Standard startup path: `./init.sh`, or `uvicorn gauntlet.app:app --reload --port 8000` after install.
- Standard verification path: `python -m py_compile gauntlet/*.py && python gauntlet/build_resolver.py`
- Current code state: fresh FastAPI/Python scaffold for GitHub App triggered sandbox runs using AWS Lambda MicroVMs.
- Highest priority unfinished feature: define the first real run contract and connect generated workflow contracts to sandbox execution.
- Current blocker: AWS Lambda MicroVM boto3 operation names are marked uncertain in `gauntlet/microvm.py`; live verification requires AWS account/API availability.

## Session Record

### 2026-06-27 - Context Harness Setup

- Goal: Build project context from the live landing page, local architecture docx, previous repo, and harness-engineering guide, then create agent context files.
- Completed:
  - Reviewed live `https://rungauntlet.tech/` landing page.
  - Extracted `agent-sandbox-architecture-summary.docx`.
  - Inspected prior repository at `/Users/aryanjain/projects/Gauntlet`.
  - Inspected current fresh scaffold in this repository.
  - Added root agent instructions and durable context files.
- Verification run: `python -m py_compile gauntlet/*.py` passed; `python gauntlet/build_resolver.py` passed with `ok`.
- Evidence recorded: see `docs/agent-context/product-brief.md`, `docs/agent-context/architecture-brief.md`, and `docs/agent-context/previous-repo-inventory.md`.
- Commits: none.
- Known risks:
  - No live AWS/GitHub integration was exercised.
  - Previous repo inventory is broad, not a full line-by-line migration audit.
  - Browser daemon was unreliable in sandbox, so landing-page context was confirmed through direct HTTP output and old source.
- Next best action: define the first real customer run contract: input config, workflow specification, egress policy, result schema, and GitHub Check summary.

### 2026-06-27 - Workflow Generation MVP Planning

- Goal: Document how automatic workflow generation should work for the MVP, including product surface coverage and service clone/twin awareness.
- Completed:
  - Researched the previous repo's Layer 0 workflow generator, docs upload path, MCP probing, native harness, and OpenClaw external harness.
  - Documented a new compiler-style workflow generation plan in `docs/agent-context/workflow-generation-mvp-plan.md`.
  - Updated `feature_list.json` so `workflow-generation-mvp` is the top-priority feature.
- Verification run: `python -m json.tool feature_list.json` passed.
- Evidence recorded: `docs/agent-context/workflow-generation-mvp-plan.md`.
- Commits: none.
- Known risks:
  - The plan is not implemented yet.
  - The fresh repo still lacks workflow generation modules, tests, storage, and run-contract integration.
- Next best action: implement `gauntlet/workflows/schema.py`, `probe.py`, `service_map.py`, `validate.py`, and a fake-planner test suite before adding provider calls.

### 2026-06-27 - Workflow Generation MVP Implementation

- Goal: Implement `docs/agent-context/workflow-generation-mvp-plan.md` with high-quality automatic workflow generation and service clone/twin awareness.
- Completed:
  - Added `gauntlet/workflows/` package with typed generation contracts, product surface probing, service/twin mapping, capability graph construction, MCP tool discovery, deterministic candidate generation, validation, and coverage selection.
  - Added `POST /workflows/generate` with typed request validation.
  - Added focused end-to-end tests for multi-service twin workflows, MCP discovery, unsafe workflow rejection, record-mode mutation rejection, API response shape, malformed request UX, and egress safety.
  - Made `gauntlet.app` import the runner lazily so workflow-only tests do not require AWS dependencies such as `boto3`.
- Verification run:
  - `python -m py_compile gauntlet/*.py gauntlet/workflows/*.py` passed.
  - `python -m unittest tests.test_workflow_generation` passed: 7 tests.
  - `python gauntlet/build_resolver.py` passed with `ok`.
- Evidence recorded: `feature_list.json` status for `workflow-generation-mvp` is `passing`.
- Commits: none.
- Known risks:
  - Generation is deterministic and rules-based for the MVP; no LLM planner/provider repair pass has been added yet.
  - Generated workflow contracts are not yet executed by the sandbox runner.
  - There is no persistence/review UI yet.
- Next best action: implement `run-contract-v1` so generated workflows can be selected and executed inside the sandbox with artifact/result reporting.

### 2026-06-27 - Hybrid Planner And Harness Scoring Upgrade

- Goal: Upgrade workflow generation from deterministic-only generation to a hybrid high-quality system using prior art from the old Gauntlet LLM planner, optional LLM candidates/repair, and harness-style quality gates.
- Completed:
  - Added `RuleBasedPlanner` and moved deterministic candidates behind a planner interface.
  - Added `LLMPlanner` using an OpenAI-compatible chat endpoint via `GAUNTLET_PLANNER_API_KEY` or `OPENAI_API_KEY`, with fakeable prompt sender for tests.
  - Added LLM repair pass for rejected candidates; deterministic validation remains the hard gate.
  - Added `GauntletNativeDryRunScorer` to simulate harness feasibility and reject generic or unjudgeable workflows before coverage selection.
  - Added `target_interfaces` to workflow contracts and coverage reporting.
  - Added stronger rules fallback that produces concrete workflow target workflows from docs: session lifecycle, direct scrape, profiles/auth context, files, and agent traces.
  - Added API fields: `planner`, `planner_model`, and `repair_attempts`.
- Verification run:
  - `python -m py_compile gauntlet/*.py gauntlet/workflows/*.py` passed.
  - `python -m unittest tests.test_workflow_generation` passed: 10 tests.
  - `python gauntlet/build_resolver.py` passed with `ok`.
  - `python -m json.tool feature_list.json` passed.
- Real product docs sample now generates five specific workflows covering Sessions API, Browser Tools, Profiles API, Files API, and Agent Traces, with interface coverage across browser, CLI, REST, and Python SDK.
- Known risks:
  - LLM provider calls are implemented but not live-tested with a real provider key in this session.
  - Harness scoring is still a dry-run quality gate; it does not execute customer code or service twins yet.
  - No persistence/review UI exists yet.
- Next best action: implement `run-contract-v1` and connect generated workflow contracts to sandbox execution, artifacts, scoring, and GitHub Check output.

### 2026-07-03 - run-contract-v1 (UI ↔ Backend Dispatch)

- Goal: Wire the UI "Run Workflow" button to actual sandbox execution via the backend, with real-time status via Supabase.
- Completed:
  - Extended old backend `POST /api/sandbox/trigger` (in `/Users/aryanjain/projects/Gauntlet/gauntlet/server/routes/sandbox_runner.py`) to accept and forward workflow params: `task_prompt`, `twins`, `modes`, `workflow_id`, `egress_default`, `callback_url`, `callback_secret`. The runner Job now carries these fields to the MicroVM execution layer.
  - Updated `web/src/app/api/sandboxes/[id]/runs/route.ts` POST handler:
    - After creating the run row in Supabase (status: queued), resolves GitHub installation_id from the backend.
    - Resolves the HEAD SHA for the sandbox's repo+branch via the backend branches endpoint.
    - Dispatches to `/api/sandbox/trigger` with all workflow params and a callback URL pointing to `POST /api/runs/[id]/result`.
    - If dispatch or SHA resolution fails, immediately updates run to status: error with a descriptive message.
  - Added `web/src/app/api/runs/[id]/result/route.ts` — the callback endpoint the runner POSTs to when execution completes. Verifies `SANDBOX_CALLBACK_SECRET` via `Authorization: Bearer`, parses `{status, verdict, trajectory, error, exit_code}`, maps runner status to Supabase status values, and writes `finished_at`, `verdict`, `trajectory`, `error` to the `sandbox_runs` row.
  - Updated branches route to pass through `commit_sha` from the backend so the frontend can also show/use branch SHAs.
  - Added `NEXT_PUBLIC_APP_URL` and `SANDBOX_CALLBACK_SECRET` to `.env.example`.
- Verification:
  - `npm run lint`: passed.
  - `npm run build`: passed.
  - Python AST syntax check on modified sandbox_runner.py: passed.
- Known gaps:
  - Old backend changes not yet deployed to Fly.io — requires `cd /Users/aryanjain/projects/Gauntlet && flyctl deploy`.
  - End-to-end execution requires MicroVM/S3 infra configured.
  - `SANDBOX_CALLBACK_SECRET` and `NEXT_PUBLIC_APP_URL` must be set in both the Next.js env and the Fly backend env.
  - Local dev: callback URL on localhost won't be reachable by Fly — runs will stay "queued" until a public URL (ngrok/Vercel) is used.
- Next best action: deploy backend changes, set env vars, and test end-to-end run flow. Then implement `egress-policy-v1`.
