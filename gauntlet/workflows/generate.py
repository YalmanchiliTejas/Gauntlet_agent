"""Compiler-style automatic workflow generation MVP."""

from __future__ import annotations

from typing import Any
import re

from .graph import build_capability_graph
from .mcp_probe import fetch_mcp_tools
from .probe import build_surface_map, parse_docs, parse_repo
from .quality import normalize_workflow_quality
from .harness import GauntletNativeDryRunScorer
from .llm_planner import LLMPlanner
from .rules_planner import RuleBasedPlanner
from .schema import (
    RejectedWorkflow,
    ServiceDependency,
    ValidationIssue,
    WorkflowDraft,
    WorkflowGenerationRequest,
    WorkflowGenerationResponse,
    to_plain,
)
from .select import select_workflows
from .service_map import build_service_map, egress_for_services
from .validate import validate_workflow


def generate_workflows(payload: dict[str, Any] | WorkflowGenerationRequest) -> WorkflowGenerationResponse:
    request = payload if isinstance(payload, WorkflowGenerationRequest) else parse_request(payload)
    if request.mcp_server_url and not request.mcp_tools:
        request.mcp_tools = fetch_mcp_tools(request.mcp_server_url)
    request.services = _with_inferred_first_party_services(request)
    service_map = build_service_map(request.services)
    surface_map = build_surface_map(request.docs, request.repo, request.mcp_tools, request.declared_secrets)
    capability_graph = build_capability_graph(surface_map, service_map.services)
    planners = _choose_planners(request)
    candidates: list[WorkflowDraft] = []
    for planner in planners:
        candidates.extend(
            planner.generate_candidates(
                request,
                surface_map,
                service_map if isinstance(planner, LLMPlanner) else service_map.services,
            )
        )

    accepted: list[WorkflowDraft] = []
    rejected: list[RejectedWorkflow] = []
    scorer = GauntletNativeDryRunScorer()
    harness_results = []
    for candidate in candidates:
        candidate = normalize_workflow_quality(candidate)
        issues = validate_workflow(
            candidate,
            surface_map,
            service_map,
            request.declared_secrets,
            request.live_service_approval,
            request.egress_domains,
        )
        repair_planner = next((item for item in planners if isinstance(item, LLMPlanner)), None)
        if issues and repair_planner is not None and request.repair_attempts > 0:
            repaired = repair_planner.repair_candidate(
                candidate,
                [f"{issue.code}: {issue.message}" for issue in issues],
                request,
                surface_map,
                service_map,
            )
            if repaired is not None:
                repaired = normalize_workflow_quality(repaired)
                repaired_issues = validate_workflow(
                    repaired,
                    surface_map,
                    service_map,
                    request.declared_secrets,
                    request.live_service_approval,
                    request.egress_domains,
                )
                if not repaired_issues:
                    candidate = repaired
                    issues = []
        if issues:
            rejected.append(RejectedWorkflow(name=candidate.name, reasons=issues))
        else:
            dry_run = scorer.score(candidate, surface_map, service_map)
            harness_results.append(dry_run)
            if dry_run.feasible:
                accepted.append(candidate)
            else:
                defect_reasons = [
                    ValidationIssue(
                        code=defect.code,
                        message=defect.message,
                        severity=defect.severity,
                        workflow_name=candidate.name,
                    )
                    for defect in dry_run.defects
                    if defect.severity == "error"
                ]
                rejected.append(
                    RejectedWorkflow(
                        name=candidate.name,
                        reasons=defect_reasons
                        or [
                            ValidationIssue(
                                code="harness_dry_run_failed",
                                message=f"Dry-run score {dry_run.score}/100 is below feasibility threshold.",
                                workflow_name=candidate.name,
                            )
                        ],
                    )
                )

    count = int(request.coverage.get("count") or 5)
    selected, report = select_workflows(accepted, rejected, surface_map, service_map, max(1, min(count, 12)), harness_results)
    return WorkflowGenerationResponse(
        surface_map=surface_map,
        service_map=service_map,
        capability_graph=capability_graph,
        coverage_report=report,
        workflows=selected,
    )


def generate_workflows_json(payload: dict[str, Any]) -> dict[str, Any]:
    return to_plain(generate_workflows(payload))


def parse_request(payload: dict[str, Any]) -> WorkflowGenerationRequest:
    docs = parse_docs(payload.get("docs") or [])
    repo = parse_repo(payload.get("repo"))
    services = payload.get("services") or []
    mcp_tools = payload.get("mcp_tools") or []
    declared_secrets = _string_list(payload.get("declared_secrets") or payload.get("secrets"))
    egress_domains = _string_list(payload.get("egress_domains"))
    return WorkflowGenerationRequest(
        docs=docs,
        mcp_server_url=str(payload.get("mcp_server_url")) if payload.get("mcp_server_url") else None,
        mcp_tools=[tool for tool in mcp_tools if isinstance(tool, dict)],
        repo=repo,
        services=services,
        declared_secrets=declared_secrets,
        egress_domains=egress_domains,
        live_service_approval=bool(payload.get("live_service_approval", False)),
        focus=str(payload.get("focus")).strip() or None if payload.get("focus") else None,
        coverage=payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {},
        planner=str(payload.get("planner") or "auto") if str(payload.get("planner") or "auto") in {"auto", "rules", "llm"} else "auto",
        planner_model=str(payload.get("planner_model")) if payload.get("planner_model") else None,
        repair_attempts=int(payload.get("repair_attempts", 1)),
        combine_rule_candidates=bool(payload.get("combine_rule_candidates", True)),
    )


def _choose_planners(request: WorkflowGenerationRequest):
    rules = RuleBasedPlanner()
    if request.planner == "rules":
        return [rules]
    llm = LLMPlanner(model=request.planner_model)
    if request.planner == "llm":
        return [llm, rules] if request.combine_rule_candidates else [llm]
    if llm.available():
        return [llm, rules] if request.combine_rule_candidates else [llm]
    return [rules]


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def _infer_doc_domains(docs) -> list[str]:
    domains: set[str] = set()
    for doc in docs:
        for match in re.findall(r"https?://([A-Za-z0-9.-]+)", doc.text):
            domains.add(match.lower())
        for match in re.findall(r"wss?://([A-Za-z0-9.-]+)", doc.text):
            domains.add(match.lower())
    return sorted(domains)


def _with_inferred_first_party_services(request: WorkflowGenerationRequest) -> list:
    services = list(request.services)
    known = {
        (service.name if isinstance(service, ServiceDependency) else str(service.get("name") or service.get("service") or "")).lower()
        for service in services
        if isinstance(service, ServiceDependency) or isinstance(service, dict)
    }
    docs_text = "\n".join(doc.text for doc in request.docs)
    domain = _infer_primary_api_domain(docs_text)
    if domain and "primary_api" not in known:
        services.append(
            ServiceDependency(
                name="primary_api",
                mode="twin",
                capabilities=[
                    "call documented API endpoints",
                    "create documented resources",
                    "read documented resources",
                    "update documented resources",
                    "fetch documented events",
                ],
                allowed_side_effects=["create_resource", "update_resource", "release_resource", "upload_artifact"],
                observable_state=["resources", "artifacts", "events", "logs"],
                domain=domain,
                version="docs",
            )
        )
    return services


def _infer_primary_api_domain(text: str) -> str | None:
    patterns = [
        r"(?:api\s+base\s+url|base\s+url|base_url|endpoint)\s*[:=]\s*`?https?://([A-Za-z0-9.-]+)",
        r"(?:api\s+base\s+url|base\s+url|base_url|endpoint)\s*[:=]\s*`?wss?://([A-Za-z0-9.-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return None
