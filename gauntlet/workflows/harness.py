"""Harness-style dry-run scoring for generated workflows.

This does not execute customer code yet. It simulates the checks a controlled
Gauntlet MCP-bound harness would need: concrete prompt, allowed interfaces,
declared routing, observable evidence, seed data, and cleanup.
"""

from __future__ import annotations

from .schema import HarnessCheck, HarnessDryRunResult, ProductSurfaceMap, ServiceMap, WorkflowDraft


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
                workflow.cleanup_required or not _has_mutation(workflow),
                10,
            ),
        ]
        score = sum(check.points for check in checks if check.passed)
        notes = []
        if score < 70:
            notes.append("Workflow is likely too generic or under-specified for a real agent harness.")
        if workflow.services and not workflow.egress_policy:
            notes.append("Service workflow lacks egress policy.")
        return HarnessDryRunResult(
            workflow_name=workflow.name,
            feasible=score >= 70,
            score=score,
            checks=checks,
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
    if "cli" in interfaces and any(word in lower for word in ("cli", "command", "steel scrape")):
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
    seed_services = {seed.service for seed in workflow.seed_data}
    return all(service.name in seed_services for service in workflow.services)


def _has_mutation(workflow: WorkflowDraft) -> bool:
    if workflow.services and all(service.mode == "twin" and not service.cleanup_required for service in workflow.services):
        return False
    text = " ".join(
        [
            workflow.task_prompt,
            " ".join(workflow.expected_state_transitions),
            " ".join(service_cap for service in workflow.services for service_cap in service.capabilities),
        ]
    ).lower()
    return any(word in text for word in ("create", "update", "delete", "post", "send", "draft", "refund", "upload", "release"))
