# Automatic Workflow Generation MVP Plan

Last updated: 2026-06-27

## Goal

Build excellent automatic workflow generation for Gauntlet's MVP.

This must not be a generic "LLM writes some prompts from docs" feature. It should behave like a product-surface compiler:

```text
product inputs
  -> product surface map
  -> service/twin map
  -> capability graph
  -> workflow candidates
  -> feasibility validation
  -> coverage selection
  -> critique and repair
  -> runnable workflow contracts
```

The output should be high-quality workflows that represent real tasks users would delegate to agents, including tasks where agents interact with cloned/twin services in sandboxed environments.

## Product Context

Gauntlet's current direction is sandboxed testing and reliability infrastructure for AI agents.

Generated workflows should test:

- Agent builders: whether their agent can complete realistic tasks inside cloned tool environments.
- Infrastructure builders: whether their product/platform survives synthetic adversarial agents.
- Multi-service workflows: whether an agent can coordinate across services such as Slack, Gmail, Calendar, Jira, GitHub, Stripe, Notion, HubSpot, browser sessions, internal APIs, and customer-specific tools.
- Twin/live routing behavior: whether workflows should run against a service twin, live endpoint, or record mode.

## Lessons From The Previous Repo

Previous repo path: `/Users/aryanjain/projects/Gauntlet`

Relevant old files:

- `gauntlet/layer0/probe.py`
- `gauntlet/layer0/synthesize.py`
- `gauntlet/layer0/workflow_schema.py`
- `gauntlet/server/routes/workflows.py`
- `gauntlet/server/routes/docs.py`
- `web/components/workflow-synthesize-form.tsx`
- `gauntlet/layer2/external_harness_runner.py`
- `gauntlet/tools/mcp_server.py`

What the old generator did well:

- Probed `llms.txt`, `llms-full.txt`, and optional MCP `tools/list`.
- Used a strong planner model to generate workflow JSON.
- Required self-contained workflows with no fake pre-existing IDs.
- Required rubrics and machine `task_spec` fields.
- Forced surface targeting when multiple interfaces existed.
- Let users review/edit generated drafts before saving.
- Preserved `task_spec` when saving.
- Enforced `task_spec.required_interfaces` during native harness execution.
- Supported an advanced `openclaw` external harness path where OpenClaw executed through Gauntlet's MCP tools, preserving transcript and credential isolation.

What must improve:

- Do not expose `docs` / `docs_full` fields and then ignore them.
- Do not rely on one giant generation prompt as the only quality gate.
- Add deterministic validation and scoring.
- Add explicit service/twin awareness.
- Add coverage targets across product areas, interfaces, services, state transitions, and failure modes.
- Add visible reasoning about why workflows were selected or rejected.
- Do not require Supabase/vector embeddings for the MVP generator unless persistence/search requires it later.

## Core Principle

Generated workflows should answer:

> What can an agent actually do with this product and its connected services, through which interfaces, with what prerequisites, side effects, state transitions, and observable proof of success?

Every generated workflow must be:

- Realistic.
- Self-contained or backed by declared seed data.
- Runnable inside a sandbox.
- Grounded in discovered product/service capabilities.
- Judgeable from transcript, artifacts, service state, or twin state.
- Explicit about service routing and side effects.
- Useful for identifying product, docs, tool, runtime, environment, or agent failures.

## Inputs

MVP generator should accept these inputs directly.

### Product Inputs

- Documentation text, uploaded files, or URLs.
- `llms.txt` and `llms-full.txt` when available.
- OpenAPI specs, SDK docs, CLI docs, README, onboarding docs.
- Repo config such as Dockerfile, `.gauntlet.json`, package manifests, and test commands.
- Optional MCP server URL or MCP tool manifest.

### Sandbox Inputs

- Declared service dependencies.
- Declared secret names.
- Declared egress domains.
- Time/resource budget.
- Agent entrypoint or command.
- Available twins/clones and their versions.
- Seed data records available per service.

### Service/Twin Inputs

Services must be first-class generation context, not an afterthought.

For each service, capture:

```json
{
  "service": "slack",
  "mode": "twin",
  "version": "2026-06",
  "capabilities": ["list channels", "post message", "read thread"],
  "seed_data": ["channel: #support", "user: Alex", "thread with unresolved ticket"],
  "allowed_side_effects": ["post_message"],
  "forbidden_side_effects": ["notify_external_user"],
  "observable_state": ["messages", "threads", "reactions"],
  "cleanup_required": false
}
```

The generator should know whether a workflow can safely mutate a twin, must use record mode, or requires explicit live-mode approval.

## Product Surface Map

First pass should produce a structured surface map.

Example:

```json
{
  "interfaces": ["rest", "sdk:python", "cli", "mcp", "browser"],
  "capabilities": [
    {
      "name": "create browser session",
      "surface_area": "browser sessions",
      "interfaces": ["rest", "sdk:python"],
      "inputs": ["url", "profile_id?"],
      "outputs": ["session_id"],
      "side_effects": ["creates_session"],
      "prerequisites": ["STEEL_API_KEY"],
      "evidence": ["200 response", "returned session id"]
    }
  ],
  "entities": ["session", "profile", "scrape result", "file artifact"],
  "dangerous_operations": ["delete", "send email", "charge card"],
  "auth_requirements": ["STEEL_API_KEY"]
}
```

The surface map should be validated before generating workflows.

## Service Interaction Map

Second pass should produce a map of services/clones/twins the workflow generator may use.

Example:

```json
{
  "services": [
    {
      "name": "gmail",
      "mode": "twin",
      "capabilities": ["search inbox", "read message", "draft reply"],
      "entities": ["message", "thread", "draft"],
      "seed_data": [
        {
          "id": "email_support_refund_001",
          "description": "Customer asks for refund status and includes order id."
        }
      ],
      "state_assertions": [
        "A draft exists in the support thread.",
        "The draft references the original order id."
      ]
    },
    {
      "name": "stripe",
      "mode": "twin",
      "capabilities": ["lookup customer", "lookup payment", "create refund"],
      "entities": ["customer", "payment", "refund"],
      "dangerous_operations": ["create refund"],
      "state_assertions": [
        "Refund object was created in the twin.",
        "Refund amount matches the workflow criteria."
      ]
    }
  ]
}
```

This map should drive multi-service workflows.

## Capability Graph

Use the surface and service maps to infer chains.

Examples:

```text
create browser session -> navigate -> scrape -> screenshot -> summarize -> close session
```

```text
read support email in Gmail twin -> look up order in internal API twin -> check payment in Stripe twin -> draft response in Gmail twin -> post summary to Slack twin
```

Each capability should be classified:

- Setup capability.
- Core value capability.
- Read-only capability.
- Mutation capability.
- Cleanup capability.
- Verification capability.
- Recovery capability.

Good workflows combine these deliberately.

## Coverage Targets

Do not ask the planner for `N` generic workflows. Ask it to fill a coverage matrix.

Coverage dimensions:

- Product surface area.
- Interface: REST, SDK, CLI, MCP, browser.
- Service: Slack, Gmail, Calendar, Jira, GitHub, Stripe, internal APIs, etc.
- Service mode: twin, live, record.
- Task shape: read, create, update, delete, multi-step, recovery.
- State shape: stateless, creates state, uses returned ID, uses seeded record, cleanup required.
- Difficulty: smoke, core, long-running, adversarial, recovery.
- Failure mode: missing docs, wrong interface, auth/config issue, state mismatch, false success, cleanup failure.
- Audience: agent builder or infrastructure builder.

Selected workflows should maximize meaningful coverage without duplicates.

## Workflow Quality Bar

Every generated workflow must include:

- Human-readable name.
- Description.
- Audience.
- Product surface area.
- Service coverage.
- Task prompt.
- Required secrets by name only.
- Egress policy.
- Twin/live/record routing.
- Seed data requirements.
- Expected state transitions.
- Success conditions.
- Rubric.
- Failure modes tested.
- Difficulty.
- Cleanup expectations.

Example shape:

```json
{
  "name": "Resolve refund request across email, orders, and payments",
  "audience": "agent_builder",
  "workflow_type": "agent_under_test",
  "surface_area": "customer support automation",
  "services": [
    {"name": "gmail", "mode": "twin"},
    {"name": "internal_orders", "mode": "twin"},
    {"name": "stripe", "mode": "twin"},
    {"name": "slack", "mode": "twin"}
  ],
  "task_prompt": "Find the customer email asking about refund status, look up the order and payment, draft a reply with the status, and post a short internal summary to the support Slack channel.",
  "setup": {
    "required_secrets": [],
    "seed_data": [
      "gmail.thread:refund-request-001",
      "orders.order:ord_1001",
      "stripe.payment:pay_1001",
      "slack.channel:support"
    ],
    "egress_policy": [
      {"domain": "gmail.local", "mode": "twin"},
      {"domain": "orders.local", "mode": "twin"},
      {"domain": "stripe.local", "mode": "twin"},
      {"domain": "slack.local", "mode": "twin"}
    ]
  },
  "success_conditions": [
    "The agent read the seeded Gmail refund request thread.",
    "The agent looked up the matching order and payment records using identifiers from the email or returned service data.",
    "A Gmail draft reply was created in the same thread and includes the correct refund status.",
    "A Slack message was posted to the support channel with the customer, order id, and refund status.",
    "The final answer cites the actions completed and does not invent data not present in tool or service output."
  ],
  "rubric": [
    "The agent completed the task end-to-end instead of only describing a plan.",
    "Every identifier used came from seed data, the user's prompt, or a prior service response in this run.",
    "The workflow used the declared service twins and did not attempt undeclared live egress.",
    "The final response is grounded in observed service state or tool output."
  ],
  "failure_modes_tested": ["multi-service state chaining", "identifier grounding", "false success", "service side-effect verification"],
  "difficulty": "hard",
  "cleanup": {"required": false}
}
```

## Validation Rules

Reject generated workflows when:

- They mention capabilities not present in the surface or service map.
- They require fake or placeholder IDs.
- They depend on pre-existing resources not provided as seed data.
- They require unknown secrets.
- They use undeclared domains.
- They route to live services without explicit live-mode approval.
- They mutate services that are not twins or explicitly safe.
- Their success criteria are vague.
- They can be answered from memory without executing tools or observing state.
- They lack concrete artifact, transcript, service-state, or twin-state evidence.
- They duplicate another workflow's capability and service path.

## Critique And Repair Pass

After candidate generation, run a second pass that asks:

- Is this a real task a user would delegate to an agent?
- Are all prerequisites available?
- Is the service/twin routing clear?
- Does it test a meaningful product promise?
- Is it too easy, too broad, or too generic?
- Can success be judged from transcript, artifacts, or service state?
- Does it cover a distinct area of the product/service surface?
- What hidden reason would make this fail in a sandbox?

Repair the workflow if possible. Otherwise discard it and generate a replacement.

## MVP Architecture

Recommended first implementation modules:

```text
gauntlet/workflows/schema.py
gauntlet/workflows/probe.py
gauntlet/workflows/service_map.py
gauntlet/workflows/generate.py
gauntlet/workflows/validate.py
gauntlet/workflows/select.py
gauntlet/routes/workflows.py
tests/test_workflow_generation.py
```

### `schema.py`

Owns typed models:

- `ProductSurfaceMap`
- `ServiceMap`
- `ServiceDependency`
- `TwinRequirement`
- `WorkflowDraft`
- `WorkflowContract`
- `EgressRule`
- `SeedDataRequirement`
- `SuccessCondition`

Use Pydantic if the project already depends on FastAPI/Pydantic. Otherwise dataclasses are acceptable for early internal-only code.

### `probe.py`

Builds raw product context from:

- docs text/URL/files,
- MCP tools/list,
- repo config,
- declared services,
- declared secrets,
- egress domains.

### `service_map.py`

Normalizes declared services and available twins/clones.

This is where service/twin awareness belongs.

### `generate.py`

Runs planner model in stages:

1. Extract surface map.
2. Extract service map if not supplied.
3. Generate candidate workflows against coverage targets.
4. Critique and repair selected candidates.

### `validate.py`

Performs deterministic checks.

No workflow reaches the user without passing this module.

### `select.py`

Scores and selects workflows by coverage.

The selection output should explain:

- which product/service areas are covered,
- which areas are uncovered,
- which candidates were rejected and why.

## API Shape

MVP endpoint can be simple and direct:

```http
POST /workflows/generate
```

Request:

```json
{
  "docs": [{"title": "llms-full.txt", "text": "..."}],
  "mcp_server_url": "https://mcp.example.com/jsonrpc",
  "repo": {
    "runtime": "python",
    "entrypoint": "python agent.py"
  },
  "services": [
    {
      "name": "slack",
      "mode": "twin",
      "capabilities": ["read channel", "post message"],
      "seed_data": ["channel:support"]
    }
  ],
  "coverage": {
    "count": 5,
    "include_multi_service": true,
    "include_recovery": true,
    "include_adversarial": true
  }
}
```

Response:

```json
{
  "surface_map": {},
  "service_map": {},
  "coverage_report": {
    "covered_surface_areas": [],
    "covered_services": [],
    "rejected_candidates": []
  },
  "workflows": []
}
```

## External Harness Note

The old repo supported OpenClaw as an advanced external harness:

- `gauntlet` native harness.
- `openclaw` external harness.

OpenClaw was configured to use Gauntlet's MCP tools and had native exec denied. This was valuable because external agents could reason independently while Gauntlet still owned:

- credential isolation,
- execution policy,
- tool transcript capture,
- artifacts,
- final judging.

For this MVP, do not start by re-implementing OpenClaw. Design workflow contracts so they can later declare compatible harnesses:

```json
{
  "execution_harness": "gauntlet-native",
  "compatible_harnesses": ["gauntlet-native", "external-mcp-agent"]
}
```

Preserve the MCP-tool boundary as a future integration point.

## Implemented Hybrid Planner Direction

The MVP implementation now uses a hybrid path:

```text
rules planner fallback
  + optional LLM planner candidate generation
  + optional LLM repair pass
  -> deterministic validation
  -> Gauntlet native dry-run scoring
  -> coverage selection
```

The LLM planner is only a candidate source. It does not bypass validation.

Use:

```json
{
  "planner": "auto"
}
```

for automatic behavior. `auto` uses the LLM planner when `GAUNTLET_PLANNER_API_KEY` or `OPENAI_API_KEY` is configured, otherwise it falls back to the rules planner.

Use:

```json
{
  "planner": "rules"
}
```

for deterministic local generation, and:

```json
{
  "planner": "llm",
  "repair_attempts": 1
}
```

to require LLM generation.

The dry-run scorer is intentionally not an execution harness yet. It checks whether a workflow looks runnable by a controlled Gauntlet harness: concrete prompt, interface targeting, declared routing, seed grounding, observable evidence, cleanup expectations, and judgeable success conditions.

## What "Amazing" Looks Like

The product should be able to show the user:

- "We found 8 product areas and 5 service dependencies."
- "Generated workflows cover REST, SDK, browser, Gmail twin, Slack twin, and Stripe twin."
- "Rejected 4 candidate workflows because they required unavailable profile IDs or undeclared live egress."
- "This workflow requires the Stripe twin because it creates a refund."
- "This workflow tests multi-service state chaining and false-success risk."
- "These workflows cover 80% of documented core capabilities and all declared service twins."

This visible reasoning is the difference between prompt generation and serious agent testing infrastructure.
