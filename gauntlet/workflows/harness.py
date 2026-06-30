"""Harness-style dry-run scoring for generated workflows.

This does not execute customer code yet. It simulates the checks a controlled
Gauntlet MCP-bound harness would need: concrete prompt, allowed interfaces,
declared routing, observable evidence, seed data, and cleanup.
"""

from __future__ import annotations

import re
from typing import Any

from .schema import HarnessCheck, HarnessDefect, HarnessDryRunResult, ProductSurfaceMap, ServiceMap, WorkflowDraft


class GauntletNativeDryRunScorer:
    name = "gauntlet-native-dry-run"

    def score(
        self,
        workflow: WorkflowDraft,
        surface_map: ProductSurfaceMap,
        service_map: ServiceMap,
    ) -> HarnessDryRunResult:
        checks = [
            _check(
                "specific_prompt",
                "Task prompt is concrete enough for an agent to attempt.",
                _specific_prompt(workflow.task_prompt),
                15,
            ),
            _check(
                "interface_targeted",
                "Workflow targets at least one discovered product interface.",
                _interface_targeted(workflow, surface_map),
                15,
            ),
            _check(
                "observable_evidence",
                "Success conditions include non-transcript observable evidence.",
                any(cond.evidence in {"artifact", "api_response", "service_state", "twin_state"} for cond in workflow.success_conditions),
                20,
            ),
            _check(
                "service_routing",
                "Declared service workflows include matching egress policy.",
                _service_routing(workflow),
                15,
            ),
            _check(
                "seed_grounding",
                "Stateful service workflows are grounded in seed data.",
                _seed_grounding(workflow),
                10,
            ),
            _check(
                "judgeable_rubric",
                "Rubric and success conditions are strong enough for judging.",
                len(workflow.rubric) >= 3 and len(workflow.success_conditions) >= 3,
                15,
            ),
            _check(
                "cleanup_or_readonly",
                "Workflow either declares cleanup or is read-only/short-lived.",
                _cleanup_or_readonly(workflow),
                10,
            ),
            _check(
                "literal_inputs",
                "Workflow declares literal fixtures or contains deterministic literal inputs.",
                _has_literal_inputs(workflow),
                10,
            ),
            _check(
                "resource_id_chain",
                "Workflow creates or obtains an identifier and uses it in later steps.",
                _has_resource_id_chain(workflow),
                10,
            ),
            _check(
                "machine_oracle",
                "Workflow has a machine-checkable oracle tied to a field, artifact, status, or exact value.",
                _has_machine_oracle(workflow),
                15,
            ),
        ]
        defects = _detect_defects(workflow, surface_map, service_map)
        readiness = _readiness(workflow, defects)
        risk_level = _risk_level(workflow)
        score = sum(check.points for check in checks if check.passed)
        score -= 40 * len([defect for defect in defects if defect.severity == "error"])
        score -= 10 * len([defect for defect in defects if defect.severity == "warning"])
        score = max(score, 0)
        notes = []
        if score < 70:
            notes.append("Workflow is likely too generic or under-specified for a real agent harness.")
        if workflow.services and not workflow.egress_policy:
            notes.append("Service workflow lacks egress policy.")
        if defects:
            notes.extend(f"{defect.code}: {defect.message}" for defect in defects[:5])
        return HarnessDryRunResult(
            workflow_name=workflow.name,
            feasible=score >= 85 and not any(defect.severity == "error" for defect in defects),
            score=score,
            checks=checks,
            defects=defects,
            readiness=readiness,
            risk_level=risk_level,
            notes=notes,
        )


def _check(code: str, message: str, passed: bool, points: int) -> HarnessCheck:
    return HarnessCheck(code=code, message=message, passed=passed, points=points)


def _specific_prompt(prompt: str) -> bool:
    lower = prompt.lower()
    action_words = ("use", "perform", "coordinate", "create", "connect", "navigate", "scrape", "capture", "upload", "download", "release", "verify", "post", "draft", "lookup")
    return len(prompt.split()) >= 20 and any(word in lower for word in action_words)


def _interface_targeted(workflow: WorkflowDraft, surface_map: ProductSurfaceMap) -> bool:
    if workflow.target_interfaces:
        discovered = set(surface_map.interfaces)
        return all(interface in discovered or (interface.startswith("sdk:") and any(item.startswith("sdk") for item in discovered)) for interface in workflow.target_interfaces)
    lower = workflow.task_prompt.lower()
    interfaces = set(surface_map.interfaces)
    if "cli" in interfaces and any(word in lower for word in ("cli", "command", "$ ", "npx ", "uvx ")):
        return True
    if "rest" in interfaces and any(word in lower for word in ("rest", "http", "api", "endpoint", "curl")):
        return True
    if any(interface.startswith("sdk") for interface in interfaces) and any(word in lower for word in ("sdk", "python", "typescript", "javascript", "client")):
        return True
    if "browser" in interfaces and any(word in lower for word in ("browser", "playwright", "puppeteer", "navigate", "screenshot")):
        return True
    if "mcp" in interfaces and "mcp" in lower:
        return True
    return len(interfaces) <= 1


def _service_routing(workflow: WorkflowDraft) -> bool:
    if not workflow.services:
        return True
    rule_services = {rule.service for rule in workflow.egress_policy}
    return all(service.name in rule_services for service in workflow.services)


def _seed_grounding(workflow: WorkflowDraft) -> bool:
    if not workflow.services:
        return True
    if not _has_mutation(workflow):
        return True
    if _creates_state_during_run(workflow):
        return True
    seed_services = {seed.service for seed in workflow.seed_data}
    return all(service.name in seed_services for service in workflow.services)


def _has_mutation(workflow: WorkflowDraft) -> bool:
    text = " ".join(
        [
            workflow.task_prompt,
            " ".join(workflow.expected_state_transitions),
            " ".join(service_cap for service in workflow.services for service_cap in service.capabilities),
        ]
    ).lower()
    return any(word in text for word in ("create", "update", "delete", "post", "send", "draft", "refund", "upload", "release"))


def _cleanup_or_readonly(workflow: WorkflowDraft) -> bool:
    if not _has_mutation(workflow):
        return True
    if not workflow.cleanup_required:
        return bool(workflow.expected_state_transitions)
    text = " ".join(
        [workflow.task_prompt]
        + workflow.expected_state_transitions
        + [condition.description for condition in workflow.success_conditions]
    ).lower()
    return any(word in text for word in ("release", "cleanup", "close")) and any(
        word in text for word in ("post-release", "no longer active", "terminated", "release response", "lookup", "status")
    )


def _has_literal_inputs(workflow: WorkflowDraft) -> bool:
    if workflow.test_fixtures:
        return True
    text = workflow.task_prompt
    return any(token in text for token in ("https://", "http://", ".txt", ".png", "exact", "named "))


def _has_resource_id_chain(workflow: WorkflowDraft) -> bool:
    if not _has_mutation(workflow):
        return True
    text = " ".join(
        [workflow.task_prompt]
        + workflow.expected_state_transitions
        + [condition.description for condition in workflow.success_conditions]
    ).lower()
    id_terms = ("session id", "profile id", "file id", "trace id", "returned id", "created session", "same session")
    create_terms = ("create", "created", "returns", "returned", "produced")
    use_terms = ("use", "using", "same", "release", "lookup", "fetch", "download")
    return any(term in text for term in id_terms) and any(term in text for term in create_terms) and any(term in text for term in use_terms)


def _creates_state_during_run(workflow: WorkflowDraft) -> bool:
    text = " ".join([workflow.task_prompt, " ".join(workflow.expected_state_transitions)]).lower()
    return any(phrase in text for phrase in ("create a", "create an", "creates a", "is created", "created during", "during the run"))


def _has_machine_oracle(workflow: WorkflowDraft) -> bool:
    text = " ".join([condition.description for condition in workflow.success_conditions] + workflow.expected_artifacts).lower()
    anchors = (
        "contains",
        "exactly",
        "status",
        "200",
        "404",
        "screenshot",
        "title",
        "file",
        "localstorage",
        "event id",
        "timestamp",
        "no longer active",
        "release response",
    )
    return any(anchor in text for anchor in anchors)


def _detect_defects(
    workflow: WorkflowDraft,
    surface_map: ProductSurfaceMap,
    service_map: ServiceMap,
) -> list[HarnessDefect]:
    defects: list[HarnessDefect] = []
    operation_labels = _operation_labels(workflow)

    if not operation_labels and _requires_operations(workflow):
        defects.append(
            _defect(
                "missing_concrete_operation",
                "Workflow has no concrete documented operation, endpoint, SDK call, CLI command, MCP tool, or service route.",
                "Bind the workflow to at least one extracted operation or mark it as blocked.",
            )
        )

    if "the documented product interface" in workflow.task_prompt.lower():
        defects.append(
            _defect(
                "generic_operation_placeholder",
                "Workflow still contains a generic documented-interface placeholder.",
                "Replace placeholder language with concrete operation labels from the docs.",
            )
        )

    chain_issue = _operation_chain_issue(workflow)
    if chain_issue:
        defects.append(chain_issue)

    if _has_unsafe_side_effect(workflow) and not _side_effect_is_grounded(workflow):
        defects.append(
            _defect(
                "unsafe_side_effect_without_seed",
                "Workflow includes a high-risk side effect without seed data, explicit safe fixture, or side-effect policy.",
                "Add seed data and an allowed side-effect oracle, or downgrade the workflow to blocked coverage.",
            )
        )

    if not _has_specific_oracle(workflow):
        defects.append(
            _defect(
                "weak_oracle",
                "Workflow success conditions do not name exact fields, values, statuses, artifact content, or state checks.",
                "Add machine-checkable assertions tied to fixtures or operation outputs.",
            )
        )

    if workflow.cleanup_required and not _cleanup_or_readonly(workflow):
        defects.append(
            _defect(
                "missing_cleanup_proof",
                "Workflow requires cleanup but lacks a concrete cleanup action plus post-cleanup proof.",
                "Add cleanup operation and assert status, release response, or absence after lookup.",
            )
        )

    return defects


def _defect(code: str, message: str, suggested_fix: str, severity: str = "error") -> HarnessDefect:
    return HarnessDefect(code=code, message=message, suggested_fix=suggested_fix, severity=severity)  # type: ignore[arg-type]


def _readiness(workflow: WorkflowDraft, defects: list[HarnessDefect]) -> dict[str, Any]:
    blockers = [defect.code for defect in defects if defect.severity == "error"]
    if workflow.required_secrets and not workflow.egress_policy:
        blockers.append("missing_secret_route")
    if workflow.cleanup_required and not _cleanup_or_readonly(workflow):
        blockers.append("missing_cleanup")
    return {
        "ready": not blockers,
        "blockers": sorted(set(blockers)),
        "required_secrets": workflow.required_secrets,
        "routes": [f"{rule.service}:{rule.mode}:{rule.domain}" for rule in workflow.egress_policy],
    }


def _operation_labels(workflow: WorkflowDraft) -> list[str]:
    labels: list[str] = []
    for key, value in workflow.test_fixtures.items():
        if key in {"operation", "operations"} or key.endswith("_operations"):
            if isinstance(value, list):
                labels.extend(str(item) for item in value if item)
            elif value:
                labels.append(str(value))
    for seed in workflow.seed_data:
        labels.append(seed.ref)
    return labels


def _requires_operations(workflow: WorkflowDraft) -> bool:
    if workflow.services or workflow.required_secrets or workflow.egress_policy:
        return True
    if any(interface in {"rest", "cli", "mcp"} or interface.startswith("sdk") for interface in workflow.target_interfaces):
        return True
    return False


def _operation_chain_issue(workflow: WorkflowDraft) -> HarnessDefect | None:
    create_resources = _resources_from_operations(_fixture_list(workflow, "create_operations"))
    cleanup_resources = _resources_from_operations(_fixture_list(workflow, "cleanup_operations"))
    if len(create_resources) > 1:
        return _defect(
            "operation_chain_incompatible",
            f"Lifecycle workflow creates multiple resource families: {', '.join(sorted(create_resources))}.",
            "Split into separate workflows or bind cleanup/assertions to one created resource.",
        )
    if create_resources and cleanup_resources and not (create_resources & cleanup_resources):
        return _defect(
            "operation_chain_incompatible",
            f"Cleanup resource {', '.join(sorted(cleanup_resources))} does not match created resource {', '.join(sorted(create_resources))}.",
            "Use cleanup operation for the same returned resource id.",
        )
    return None


def _fixture_list(workflow: WorkflowDraft, key: str) -> list[str]:
    value = workflow.test_fixtures.get(key)
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if value:
        return [str(value)]
    return []


def _resources_from_operations(labels: list[str]) -> set[str]:
    resources: set[str] = set()
    for label in labels:
        lower = label.lower()
        path_match = re.search(r"/v\d+/([a-z0-9_-]+)", lower)
        if path_match:
            resources.add(_singular(path_match.group(1)))
            continue
        dotted = re.findall(r"\.([a-z][a-z0-9_-]*s)\.", lower)
        if dotted:
            resources.add(_singular(dotted[-1]))
            continue
        dotted_call = re.findall(r"\.([a-z][a-z0-9_-]*s)\(", lower)
        if dotted_call:
            resources.add(_singular(dotted_call[-1]))
    return resources


def _singular(value: str) -> str:
    value = value.replace("_", "-")
    if value.endswith("ies"):
        return value[:-3] + "y"
    if value.endswith("s") and len(value) > 3:
        return value[:-1]
    return value


def _risk_level(workflow: WorkflowDraft) -> str:
    return "high" if _has_unsafe_side_effect(workflow) else ("medium" if _has_mutation(workflow) else "low")


def _has_unsafe_side_effect(workflow: WorkflowDraft) -> bool:
    text = " ".join(
        [
            workflow.name,
            workflow.description,
            workflow.task_prompt,
            " ".join(workflow.expected_state_transitions),
            " ".join(workflow.failure_modes_tested),
        ]
        + _operation_labels(workflow)
    ).lower()
    dangerous = ("send", "charge", "refund", "publish", "merge", "approve", "invite", "delete", "remove subscriber")
    harmless = ("release", "cleanup", "post-cleanup", "delete response", "files.delete")
    if any(term in text for term in dangerous):
        if all(term not in text for term in harmless):
            return True
        return any(term in text for term in ("refund", "charge", "send campaign", "publish", "merge", "approve", "invite"))
    return False


def _side_effect_is_grounded(workflow: WorkflowDraft) -> bool:
    fixture_blob = " ".join(str(value) for value in workflow.test_fixtures.values()).lower()
    has_safe_fixture = any(term in fixture_blob for term in ("gauntlet", "test", "example.test"))
    has_seed = bool(workflow.seed_data)
    has_policy = any(service.allowed_side_effects for service in workflow.services)
    has_state_oracle = any(condition.evidence in {"service_state", "twin_state", "api_response"} for condition in workflow.success_conditions)
    return (has_seed or has_safe_fixture or has_policy) and has_state_oracle


def _has_specific_oracle(workflow: WorkflowDraft) -> bool:
    fixture_values = []
    for value in workflow.test_fixtures.values():
        if isinstance(value, str):
            fixture_values.append(value.lower())
        elif isinstance(value, list):
            fixture_values.extend(str(item).lower() for item in value)
        elif isinstance(value, dict):
            fixture_values.extend(str(item).lower() for item in value.values())
    condition_blob = " ".join(condition.description for condition in workflow.success_conditions).lower()
    artifact_blob = " ".join(workflow.expected_artifacts).lower()
    if any(value and len(value) >= 4 and value in condition_blob for value in fixture_values):
        return True
    patterns = (
        r"\b[a-z0-9_.-]*(id|status|code|title|name|url|path|count|length|content|event|timestamp)[a-z0-9_.-]*\s*(==|=|contains|equals|is)\s*['\"]?[^'\"]{2,}",
        r"\b(status|status_code|http status)\s*(==|=|is)\s*(200|201|204|400|404)",
        r"\b(events|items|records|files)\.(length|count)\s*(>=|>|==|=)\s*\d+",
        r"\b(event id|timestamp|session id|profile id|file path|artifact id|release response|post-cleanup|post-release)\b",
    )
    if any(re.search(pattern, condition_blob) for pattern in patterns):
        return True
    return any(term in artifact_blob for term in ("file_content", "downloaded", "trace_events", "release_response", "post_cleanup_status"))
