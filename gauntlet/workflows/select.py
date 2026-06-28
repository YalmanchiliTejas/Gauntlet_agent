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

    def score(workflow: WorkflowDraft) -> tuple[int, int, int]:
        service_score = len({service.name for service in workflow.services})
        hard_score = 2 if workflow.difficulty in {"hard", "adversarial", "recovery"} else 0
        evidence_score = len({cond.evidence for cond in workflow.success_conditions})
        harness_score = harness_by_name.get(workflow.name).score if workflow.name in harness_by_name else 0
        product_specific_bonus = 25 if workflow.surface_area.lower() not in {"steel documentation", "agent instructions", "core product"} else 0
        return (
            harness_score + product_specific_bonus + service_score + hard_score + evidence_score,
            len(workflow.product_capabilities),
            len(workflow.failure_modes_tested),
        )

    for workflow in sorted(candidates, key=score, reverse=True):
        key = (
            workflow.surface_area.lower(),
            tuple(sorted(service.name for service in workflow.services)),
            workflow.difficulty,
        )
        if key in seen_keys:
            rejected.append(
                RejectedWorkflow(
                    name=workflow.name,
                    reasons=[
                        ValidationIssue(
                            code="duplicate_coverage",
                            message="Another selected workflow covers the same surface, services, and difficulty.",
                            workflow_name=workflow.name,
                        )
                    ],
                )
            )
            continue
        selected.append(workflow)
        seen_keys.add(key)
        if len(selected) >= count:
            break

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
    summary = (
        f"Selected {len(selected)} workflow(s) covering {len(covered_surfaces)} surface area(s), "
        f"{len(covered_interfaces)} interface(s), and {len(covered_services)} service(s)."
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
        summary=summary,
    )
