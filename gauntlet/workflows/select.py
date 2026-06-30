"""Coverage-aware workflow selection."""

from __future__ import annotations

from .schema import CoverageReport, HarnessDryRunResult, ProductSurfaceMap, RejectedWorkflow, ServiceMap, ValidationIssue, WorkflowDraft


def select_workflows(
    candidates: list[WorkflowDraft],
    rejected: list[RejectedWorkflow],
    surface_map: ProductSurfaceMap,
    service_map: ServiceMap,
    count: int,
    harness_results: list[HarnessDryRunResult] | None = None,
) -> tuple[list[WorkflowDraft], CoverageReport]:
    selected: list[WorkflowDraft] = []
    seen_keys: set[tuple[str, tuple[str, ...], str]] = set()
    harness_by_name = {result.workflow_name: result for result in harness_results or []}

    def base_score(workflow: WorkflowDraft) -> int:
        service_score = len({service.name for service in workflow.services})
        hard_score = 2 if workflow.difficulty in {"hard", "adversarial", "recovery"} else 0
        evidence_score = len({cond.evidence for cond in workflow.success_conditions})
        harness_score = harness_by_name.get(workflow.name).score if workflow.name in harness_by_name else 0
        product_specific_bonus = 25 if workflow.surface_area.lower() not in {"documentation", "agent instructions", "core product"} else 0
        fixture_bonus = 12 if workflow.test_fixtures else 0
        artifact_bonus = 12 if workflow.expected_artifacts else 0
        readiness_bonus = 8 if workflow.run_readiness else 0
        badge_bonus = min(len(workflow.quality_badges), 4) * 3
        generic_penalty = 20 if workflow.name.startswith(("Exercise ", "Verify ")) and not workflow.test_fixtures else 0
        return (
            harness_score
            + product_specific_bonus
            + service_score
            + hard_score
            + evidence_score
            + fixture_bonus
            + artifact_bonus
            + readiness_bonus
            + badge_bonus
            - generic_penalty
        )

    remaining = list(candidates)
    duplicate_pool: list[WorkflowDraft] = []
    covered_surfaces: set[str] = set()
    covered_interfaces: set[str] = set()
    covered_services: set[str] = set()
    covered_failures: set[str] = set()
    covered_evidence: set[str] = set()

    def marginal_score(workflow: WorkflowDraft) -> tuple[int, int]:
        interfaces = set(workflow.target_interfaces)
        services = {service.name for service in workflow.services}
        failures = set(workflow.failure_modes_tested)
        evidence = {condition.evidence for condition in workflow.success_conditions}
        marginal = 0
        if workflow.surface_area not in covered_surfaces:
            marginal += 60
        marginal += 25 * len(interfaces - covered_interfaces)
        marginal += 20 * len(services - covered_services)
        marginal += 12 * len(failures - covered_failures)
        marginal += 10 * len(evidence - covered_evidence)
        if workflow.difficulty not in {item.difficulty for item in selected}:
            marginal += 8
        if workflow.test_fixtures:
            marginal += 30
        if workflow.expected_artifacts:
            marginal += 20
        if workflow.run_readiness:
            marginal += 10
        return (marginal, base_score(workflow))

    while remaining and len(selected) < count:
        workflow = max(remaining, key=marginal_score)
        remaining.remove(workflow)
        key = (
            workflow.surface_area.lower(),
            tuple(sorted(service.name for service in workflow.services)),
            tuple(sorted(workflow.product_capabilities)),
            workflow.difficulty,
        )
        if key in seen_keys:
            duplicate_pool.append(workflow)
            continue
        selected.append(workflow)
        seen_keys.add(key)
        covered_surfaces.add(workflow.surface_area)
        covered_interfaces.update(workflow.target_interfaces)
        covered_services.update(service.name for service in workflow.services)
        covered_failures.update(workflow.failure_modes_tested)
        covered_evidence.update(condition.evidence for condition in workflow.success_conditions)

    for workflow in sorted(duplicate_pool, key=base_score, reverse=True):
        if len(selected) >= count:
            rejected.append(
                RejectedWorkflow(
                    name=workflow.name,
                    reasons=[
                        ValidationIssue(
                            code="duplicate_coverage",
                            message="Another selected workflow covers the same surface, services, capability, and difficulty.",
                            workflow_name=workflow.name,
                        )
                    ],
                )
            )
            continue
        selected.append(workflow)
        covered_surfaces.add(workflow.surface_area)
        covered_interfaces.update(workflow.target_interfaces)
        covered_services.update(service.name for service in workflow.services)
        covered_failures.update(workflow.failure_modes_tested)
        covered_evidence.update(condition.evidence for condition in workflow.success_conditions)

    report = build_coverage_report(selected, rejected, surface_map, service_map, harness_results or [])
    return selected, report


def build_coverage_report(
    selected: list[WorkflowDraft],
    rejected: list[RejectedWorkflow],
    surface_map: ProductSurfaceMap,
    service_map: ServiceMap,
    harness_results: list[HarnessDryRunResult] | None = None,
) -> CoverageReport:
    covered_surfaces = sorted({workflow.surface_area for workflow in selected})
    covered_services = sorted({service.name for workflow in selected for service in workflow.services})
    covered_modes = sorted({service.mode for workflow in selected for service in workflow.services})
    covered_failures = sorted({failure for workflow in selected for failure in workflow.failure_modes_tested})
    covered_interfaces = sorted(
        {
            interface
            for workflow in selected
            for interface in workflow.target_interfaces
        }
        | {
            interface
            for workflow in selected
            for cap_name in workflow.product_capabilities
            for cap in surface_map.capabilities
            if cap.name == cap_name
            for interface in cap.interfaces
        }
    )
    all_surfaces = sorted({cap.surface_area for cap in surface_map.capabilities})
    all_services = sorted({service.name for service in service_map.services})
    uncovered_surfaces = [surface for surface in all_surfaces if surface not in covered_surfaces]
    uncovered_services = [service for service in all_services if service not in covered_services]
    matrix = [
        {
            "workflow": workflow.name,
            "surface": workflow.surface_area,
            "interfaces": workflow.target_interfaces,
            "services": [service.name for service in workflow.services],
            "evidence": sorted({condition.evidence for condition in workflow.success_conditions}),
            "creates_state": any(word in " ".join(workflow.expected_state_transitions).lower() for word in ("create", "created", "upload", "draft", "post")),
            "cleanup_required": workflow.cleanup_required,
            "failure_modes": workflow.failure_modes_tested,
            "quality_badges": workflow.quality_badges,
        }
        for workflow in selected
    ]
    catches = sorted({failure for workflow in selected for failure in workflow.failure_modes_tested})[:12]
    gaps = []
    if uncovered_surfaces:
        gaps.append(f"Uncovered documented surfaces: {', '.join(uncovered_surfaces[:5])}.")
    if uncovered_services:
        gaps.append(f"Uncovered declared services: {', '.join(uncovered_services[:5])}.")
    if not any("adversarial" in workflow.difficulty or "prompt injection" in workflow.failure_modes_tested for workflow in selected):
        gaps.append("No adversarial workflow selected at this count.")
    summary = (
        f"Selected {len(selected)} workflow(s) covering {len(covered_surfaces)} surface area(s), "
        f"{len(covered_interfaces)} interface(s), and {len(covered_services)} service(s)."
    )
    suite_narrative = (
        "Selected as a balanced workflow suite across product surfaces, interfaces, observable evidence, "
        "state transitions, cleanup expectations, and failure modes."
    )
    return CoverageReport(
        covered_surface_areas=covered_surfaces,
        covered_interfaces=covered_interfaces,
        covered_services=covered_services,
        covered_service_modes=covered_modes,
        covered_failure_modes=covered_failures,
        uncovered_surface_areas=uncovered_surfaces,
        uncovered_services=uncovered_services,
        rejected_candidates=rejected,
        harness_results=harness_results or [],
        suite_narrative=suite_narrative,
        catches=catches,
        gaps=gaps,
        coverage_matrix=matrix,
        summary=summary,
    )
