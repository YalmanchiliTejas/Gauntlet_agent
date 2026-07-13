"""Generate Gauntlet workflows from local documentation files.

Examples:
  python scripts/generate_workflows.py \
    --doc product-docs.md=/tmp/product-docs.md \
    --doc api-reference.md=/tmp/api-reference.md \
    --planner llm

  python scripts/generate_workflows.py \
    --doc llms.txt=docs/llms.txt \
    --planner rules \
    --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gauntlet.workflows.generate import generate_workflows_json


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate workflow drafts from docs.")
    parser.add_argument(
        "--doc",
        action="append",
        default=[],
        metavar="TITLE=PATH",
        help="Documentation input. Can be passed multiple times, e.g. --doc llms.txt=/tmp/llms.txt",
    )
    parser.add_argument(
        "--services-json",
        default="",
        help="Optional path to a JSON file containing a list of service/twin declarations.",
    )
    parser.add_argument("--planner", choices=["auto", "rules", "llm"], default="auto")
    parser.add_argument("--count", type=int, default=5, help="Number of final workflows to select.")
    parser.add_argument(
        "--candidate-count",
        type=int,
        default=8,
        help="Number of candidate workflows to ask the LLM planner for.",
    )
    parser.add_argument("--repair-attempts", type=int, default=1)
    parser.add_argument(
        "--no-rules-fallback",
        action="store_true",
        help="When using the LLM planner, do not also include deterministic rule-based candidates.",
    )
    parser.add_argument(
        "--secret",
        action="append",
        default=[],
        help="Declared secret name, not value. Can be passed multiple times, e.g. --secret PRODUCT_API_KEY",
    )
    parser.add_argument("--json", action="store_true", help="Print the full JSON response.")
    parser.add_argument("--output", default="", help="Optional path to write the full JSON response.")
    parser.add_argument("--env-file", default=".env", help="Env file to load before running.")
    args = parser.parse_args()

    load_env(Path(args.env_file))

    docs = [parse_doc_arg(item) for item in args.doc]
    if not docs:
        parser.error("provide at least one --doc TITLE=PATH input")

    services = []
    if args.services_json:
        services = json.loads(Path(args.services_json).read_text())
        if not isinstance(services, list):
            parser.error("--services-json must contain a JSON list")

    payload: dict[str, Any] = {
        "docs": docs,
        "services": services,
        "declared_secrets": args.secret,
        "coverage": {"count": args.count, "candidate_count": args.candidate_count},
        "planner": args.planner,
        "repair_attempts": args.repair_attempts,
        "combine_rule_candidates": not args.no_rules_fallback,
    }

    result = generate_workflows_json(payload)

    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n")

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print_summary(result)

    return 0


def parse_doc_arg(value: str) -> dict[str, str]:
    if "=" not in value:
        raise SystemExit(f"--doc must be TITLE=PATH, got: {value}")
    title, raw_path = value.split("=", 1)
    path = Path(raw_path).expanduser()
    if not path.exists():
        raise SystemExit(f"doc file does not exist: {path}")
    return {"title": title.strip() or path.name, "text": path.read_text()}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def print_summary(result: dict[str, Any]) -> None:
    coverage = result["coverage_report"]
    print(coverage["summary"])
    print("Interfaces:", ", ".join(coverage["covered_interfaces"]) or "(none)")
    print("Surfaces:", ", ".join(coverage["covered_surface_areas"]) or "(none)")

    print("\nWorkflows")
    for index, workflow in enumerate(result["workflows"], 1):
        print(f"\n{index}. {workflow['name']}")
        print(f"Surface: {workflow['surface_area']}")
        print(f"Interfaces: {', '.join(workflow.get('target_interfaces') or []) or '(unspecified)'}")
        print(f"Difficulty: {workflow['difficulty']}")
        print(f"User request: {workflow.get('user_prompt') or workflow['task_prompt']}")
        print("Success conditions:")
        for condition in workflow["success_conditions"]:
            print(f"  - {condition['description']} [{condition['evidence']}]")
        print("Failure modes:", ", ".join(workflow["failure_modes_tested"]) or "(none)")

    rejected = coverage.get("rejected_candidates") or []
    if rejected:
        print("\nRejected candidates")
        for item in rejected[:12]:
            reasons = ", ".join(reason["code"] for reason in item["reasons"])
            print(f"- {item['name']} => {reasons}")


if __name__ == "__main__":
    raise SystemExit(main())
