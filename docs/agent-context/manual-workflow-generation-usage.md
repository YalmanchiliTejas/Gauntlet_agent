# Manual Workflow Generation Usage

Last updated: 2026-06-27

Use this document when manually testing Gauntlet automatic workflow generation from local documentation files.

## Script

```bash
python scripts/generate_workflows.py
```

The script loads `.env` by default, reads one or more doc files, runs the workflow generator, and prints either a readable summary or full JSON.

## Basic Setup

From the repo root:

```bash
cd /Users/aryanjain/projects/Gauntlet_agent
```

Fetch Steel docs into local files:

```bash
curl -L -s https://docs.steel.dev/llms.txt -o /tmp/steel-llms.txt
curl -L -s https://docs.steel.dev/llms-full.txt -o /tmp/steel-llms-full.txt
```

Your `.env` can include:

```bash
GEMINI_API_KEY=...
GAUNTLET_PLANNER_PROVIDER=gemini
GAUNTLET_PLANNER_MODEL=gemini-2.5-pro
```

Do not commit `.env` or paste real API keys into prompts, docs, or test fixtures.

## Recommended Commands

### Gemini LLM Planner

```bash
python scripts/generate_workflows.py \
  --doc llms.txt=/tmp/steel-llms.txt \
  --doc llms-full.txt=/tmp/steel-llms-full.txt \
  --planner llm \
  --secret STEEL_API_KEY \
  --count 5 \
  --candidate-count 10
```

### Rules Fallback

```bash
python scripts/generate_workflows.py \
  --doc llms.txt=/tmp/steel-llms.txt \
  --doc llms-full.txt=/tmp/steel-llms-full.txt \
  --planner rules \
  --secret STEEL_API_KEY \
  --count 5
```

### Save Full JSON

```bash
python scripts/generate_workflows.py \
  --doc llms.txt=/tmp/steel-llms.txt \
  --doc llms-full.txt=/tmp/steel-llms-full.txt \
  --planner llm \
  --secret STEEL_API_KEY \
  --count 5 \
  --candidate-count 10 \
  --json \
  --output /tmp/steel-workflows.json
```

## Flags

### `--doc TITLE=PATH`

Adds a documentation input file.

Can be passed multiple times.

Example:

```bash
--doc llms.txt=/tmp/steel-llms.txt
--doc llms-full.txt=/tmp/steel-llms-full.txt
```

`TITLE` is how the doc appears in generated context. `PATH` is the local file path.

### `--planner auto|rules|llm`

Controls candidate generation.

- `auto`: uses the LLM planner when a planner API key is configured; otherwise falls back to rules.
- `rules`: uses deterministic local generation only. No LLM call.
- `llm`: requires LLM generation. With the current setup, Gemini is used when `GAUNTLET_PLANNER_PROVIDER=gemini` and `GEMINI_API_KEY` is set.

### `--count N`

Final number of workflows to select after validation and scoring.

Example:

```bash
--count 5
```

This is not how many workflows the LLM generates. It is how many validated workflows Gauntlet returns.

### `--candidate-count N`

Number of raw workflow candidates to request from the LLM planner before filtering.

Example:

```bash
--candidate-count 10
```

Higher values usually improve variety and coverage, but cost more tokens and take longer.

Recommended values:

- Quick test: `--candidate-count 6 --count 3`
- Normal run: `--candidate-count 10 --count 5`
- Larger sweep: `--candidate-count 16 --count 6`

This flag mainly matters for `--planner llm` or `--planner auto` when the LLM planner is active.

### `--repair-attempts N`

How many times the LLM planner may try to repair a candidate that failed validation.

Default:

```bash
--repair-attempts 1
```

Use `0` to disable repair.

### `--secret NAME`

Declares a secret name that generated workflows are allowed to require.

Example:

```bash
--secret STEEL_API_KEY
```

This is not the secret value. It only means workflows may require a secret named `STEEL_API_KEY`.

If a workflow requires a secret that was not declared, validation rejects it with `unknown_secret`.

Can be passed multiple times:

```bash
--secret STEEL_API_KEY --secret OPENAI_API_KEY
```

### `--services-json PATH`

Optional JSON file containing service/twin declarations.

Example:

```bash
--services-json /tmp/services.json
```

Example file:

```json
[
  {
    "name": "slack",
    "mode": "twin",
    "capabilities": ["read channel", "post message"],
    "seed_data": ["slack.channel:support"],
    "allowed_side_effects": ["post_message"]
  },
  {
    "name": "gmail",
    "mode": "twin",
    "capabilities": ["search inbox", "read message", "draft reply"],
    "seed_data": ["gmail.thread:refund-request-001"],
    "allowed_side_effects": ["create_draft"]
  }
]
```

Service modes:

- `twin`: safe cloned/mock service that can be mutated.
- `record`: recorded traffic or read-only replay; mutation-oriented workflows should be rejected.
- `live`: live external service; requires explicit live approval in the API path and should be used sparingly.

### `--json`

Prints the full JSON response instead of a readable summary.

Use this when debugging or comparing raw generated contracts.

### `--output PATH`

Writes the full JSON response to a file.

Example:

```bash
--output /tmp/steel-workflows.json
```

This can be combined with or without `--json`.

### `--env-file PATH`

Loads environment variables from a custom env file instead of `.env`.

Example:

```bash
--env-file .env.local
```

## Output Shape

The full JSON contains:

- `surface_map`: discovered product interfaces, capabilities, entities, dangerous operations, and auth requirements.
- `service_map`: declared services/twins/clones.
- `capability_graph`: inferred capability chains used to derive workflows.
- `coverage_report`: selected coverage, rejected candidates, and harness dry-run results.
- `workflows`: final validated workflow drafts.

Important fields inside each workflow:

- `name`
- `description`
- `surface_area`
- `target_interfaces`
- `task_prompt`
- `required_secrets`
- `egress_policy`
- `seed_data`
- `expected_state_transitions`
- `success_conditions`
- `rubric`
- `failure_modes_tested`
- `difficulty`
- `cleanup_required`

## Quality Checklist

Good generated workflows should:

- Name a specific product surface.
- Target explicit interfaces such as `cli`, `rest`, `sdk:python`, `sdk:javascript`, `mcp`, or `browser`.
- Ask the agent to do a real task, not describe a plan.
- Use self-contained inputs or resources created during the run.
- Avoid fake IDs and placeholder resources.
- Include concrete success conditions with observable evidence.
- Include 3-5 rubric items.
- Require cleanup when sessions or resources are created.
- Cover distinct surfaces, interfaces, difficulty levels, and failure modes.

If many candidates are rejected, inspect:

```json
coverage_report.rejected_candidates
```

Common rejection codes:

- `unknown_secret`
- `unknown_service`
- `unknown_capability`
- `undeclared_egress`
- `live_without_approval`
- `placeholder_data`
- `undeclared_identifier`
- `vague_success_criteria`
- `missing_success_conditions`
- `no_observable_evidence`
- `harness_dry_run_failed`
- `duplicate_coverage`

## Practical Notes

Gemini Flash can be fast but sometimes misses strict schema details. Gemini Pro should usually produce higher-quality candidates.

If LLM output is too sparse, increase:

```bash
--candidate-count
```

If output is too slow or expensive, decrease it.

If you need a stable baseline for debugging, use:

```bash
--planner rules
```

If you want creative workflow candidates, use:

```bash
--planner llm
```
