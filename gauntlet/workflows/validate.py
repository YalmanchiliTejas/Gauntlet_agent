"""Deterministic validation for generated workflow candidates."""

from __future__ import annotations

import re

from .schema import ProductSurfaceMap, ServiceMap, ValidationIssue, WorkflowDraft

_PLACEHOLDER_RE = re.compile(r"\b(TODO|TBD|FIXME|example_|fake_|placeholder|xxx|your_|<[^>]+>)\b", re.IGNORECASE)
_VAGUE_RE = re.compile(r"\b(correctly|successfully|properly|as needed|etc\.?|appropriate)\b", re.IGNORECASE)


def validate_workflow(
    workflow: WorkflowDraft,
    surface_map: ProductSurfaceMap,
    service_map: ServiceMap,
    declared_secrets: list[str],
    live_service_approval: bool,
    declared_egress_domains: list[str] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    known_services = {service.name for service in service_map.services}
    known_caps = {cap.name for cap in surface_map.capabilities}
    known_domains = {service.domain or f"{service.name}.local" for service in service_map.services}
    known_domains.update(declared_egress_domains or [])
    declared_secret_set = set(declared_secrets) | set(surface_map.auth_requirements)

    for service in workflow.services:
        if service.name not in known_services:
            issues.append(_issue("unknown_service", f"Workflow references undeclared service '{service.name}'.", workflow))
        if service.mode == "live" and not (live_service_approval or service.live_approved):
            issues.append(_issue("live_without_approval", f"Service '{service.name}' is live without explicit approval.", workflow))
        if service.mode == "record" and _service_implies_mutation(service):
            issues.append(_issue("record_mode_mutation", f"Service '{service.name}' is record mode but the workflow implies mutation.", workflow))

    for rule in workflow.egress_policy:
        if rule.domain not in known_domains:
            issues.append(_issue("undeclared_egress", f"Egress domain '{rule.domain}' is not declared by any service.", workflow))
        if rule.mode == "live" and not (live_service_approval or rule.approved):
            issues.append(_issue("live_egress_without_approval", f"Live egress '{rule.domain}' lacks approval.", workflow))

    for cap in workflow.product_capabilities:
        if known_caps and cap not in known_caps:
            issues.append(_issue("unknown_capability", f"Workflow references unknown capability '{cap}'.", workflow))

    for secret in workflow.required_secrets:
        if secret not in declared_secret_set:
            issues.append(_issue("unknown_secret", f"Workflow requires undeclared secret '{secret}'.", workflow))

    text_blob = " ".join(
        [
            workflow.name,
            workflow.description,
            workflow.task_prompt,
            " ".join(req.ref for req in workflow.seed_data),
            " ".join(cond.description for cond in workflow.success_conditions),
        ]
    )
    if _PLACEHOLDER_RE.search(text_blob):
        issues.append(_issue("placeholder_data", "Workflow contains placeholder or fake identifiers.", workflow))
    if _has_suspicious_undeclared_id(text_blob, {req.ref for req in workflow.seed_data}):
        issues.append(_issue("undeclared_identifier", "Workflow contains an ID-like value that is not declared as seed data.", workflow))

    if len(workflow.task_prompt.split()) < 14:
        issues.append(_issue("thin_task_prompt", "Task prompt is too short to be a real delegated workflow.", workflow))

    if len(workflow.success_conditions) < 3:
        issues.append(_issue("missing_success_conditions", "Workflow needs at least three concrete success conditions.", workflow))

    if not any(cond.evidence in {"service_state", "twin_state", "artifact", "api_response"} for cond in workflow.success_conditions):
        issues.append(_issue("no_observable_evidence", "Workflow lacks observable non-transcript evidence.", workflow))

    vague_conditions = [cond.description for cond in workflow.success_conditions if _VAGUE_RE.search(cond.description)]
    if vague_conditions:
        issues.append(_issue("vague_success_criteria", "Success criteria contain vague wording.", workflow))

    if workflow.services and not workflow.seed_data:
        mutating = any(_service_implies_mutation(service) for service in workflow.services)
        if mutating:
            issues.append(_issue("missing_seed_data", "Service workflow mutates or inspects services without seed data.", workflow))

    if not workflow.failure_modes_tested:
        issues.append(_issue("missing_failure_modes", "Workflow does not state which failure modes it tests.", workflow))

    return issues


def _issue(code: str, message: str, workflow: WorkflowDraft) -> ValidationIssue:
    return ValidationIssue(code=code, message=message, workflow_name=workflow.name)


def _service_implies_mutation(service) -> bool:
    mutating_words = ("create", "update", "delete", "post", "send", "draft", "refund", "transition", "approve")
    return bool(service.allowed_side_effects) or any(word in " ".join(service.capabilities).lower() for word in mutating_words)


def _has_suspicious_undeclared_id(text: str, declared_refs: set[str]) -> bool:
    declared_blob = " ".join(declared_refs)
    id_tokens = re.findall(r"\b[a-z][a-z0-9]{1,20}_[A-Za-z0-9_-]{2,64}\b", text)
    suspicious_parts = ("abc", "123", "42", "test", "fake", "example", "placeholder")
    for token in id_tokens:
        if token in declared_blob:
            continue
        suffix = token.split("_", 1)[1].lower()
        if any(part in suffix for part in suspicious_parts):
            return True
    return False
