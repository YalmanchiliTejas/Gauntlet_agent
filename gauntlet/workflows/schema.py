"""Typed contracts for automatic workflow generation.

The MVP keeps these as dataclasses instead of binding the core pipeline to
FastAPI/Pydantic. API handlers can accept plain JSON and the generator remains
easy to unit-test.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ServiceMode = Literal["twin", "live", "record"]
WorkflowDifficulty = Literal["smoke", "core", "hard", "adversarial", "recovery"]
PlannerMode = Literal["auto", "rules", "llm"]


@dataclass(slots=True)
class DocumentInput:
    title: str
    text: str
    url: str | None = None


@dataclass(slots=True)
class RepositoryContext:
    runtime: str | None = None
    entrypoint: str | None = None
    manifests: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EgressRule:
    domain: str
    mode: ServiceMode
    service: str | None = None
    approved: bool = False


@dataclass(slots=True)
class SeedDataRequirement:
    service: str
    ref: str
    description: str = ""


@dataclass(slots=True)
class ServiceDependency:
    name: str
    mode: ServiceMode = "twin"
    capabilities: list[str] = field(default_factory=list)
    seed_data: list[str] = field(default_factory=list)
    allowed_side_effects: list[str] = field(default_factory=list)
    forbidden_side_effects: list[str] = field(default_factory=list)
    observable_state: list[str] = field(default_factory=list)
    cleanup_required: bool = False
    domain: str | None = None
    version: str | None = None
    live_approved: bool = False


@dataclass(slots=True)
class Capability:
    name: str
    surface_area: str
    interfaces: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    source: str = "docs"


@dataclass(slots=True)
class CapabilityChain:
    name: str
    steps: list[str]
    services: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    risk_level: Literal["low", "medium", "high"] = "medium"
    reason: str = ""


@dataclass(slots=True)
class ProductSurfaceMap:
    interfaces: list[str] = field(default_factory=list)
    capabilities: list[Capability] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    dangerous_operations: list[str] = field(default_factory=list)
    auth_requirements: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ServiceMap:
    services: list[ServiceDependency] = field(default_factory=list)


@dataclass(slots=True)
class SuccessCondition:
    description: str
    evidence: Literal["transcript", "artifact", "service_state", "twin_state", "api_response"]


@dataclass(slots=True)
class WorkflowDraft:
    name: str
    description: str
    audience: Literal["agent_builder", "infrastructure_builder"]
    workflow_type: Literal["agent_under_test", "platform_under_test"]
    surface_area: str
    product_capabilities: list[str]
    services: list[ServiceDependency]
    task_prompt: str
    required_secrets: list[str]
    egress_policy: list[EgressRule]
    seed_data: list[SeedDataRequirement]
    expected_state_transitions: list[str]
    success_conditions: list[SuccessCondition]
    rubric: list[str]
    failure_modes_tested: list[str]
    difficulty: WorkflowDifficulty
    cleanup_required: bool = False
    target_interfaces: list[str] = field(default_factory=list)
    test_fixtures: dict[str, Any] = field(default_factory=dict)
    expected_artifacts: list[str] = field(default_factory=list)
    quality_badges: list[str] = field(default_factory=list)
    run_readiness: dict[str, Any] = field(default_factory=dict)
    execution_harness: str = "gauntlet-native"
    compatible_harnesses: list[str] = field(
        default_factory=lambda: ["gauntlet-native", "external-mcp-agent"]
    )
    selection_reason: str = ""


WorkflowContract = WorkflowDraft


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    workflow_name: str | None = None


@dataclass(slots=True)
class HarnessCheck:
    code: str
    message: str
    passed: bool
    points: int = 0


@dataclass(slots=True)
class HarnessDefect:
    code: str
    message: str
    severity: Literal["error", "warning"] = "error"
    suggested_fix: str = ""


@dataclass(slots=True)
class HarnessDryRunResult:
    workflow_name: str
    feasible: bool
    score: int
    checks: list[HarnessCheck] = field(default_factory=list)
    defects: list[HarnessDefect] = field(default_factory=list)
    readiness: dict[str, Any] = field(default_factory=dict)
    risk_level: Literal["low", "medium", "high"] = "medium"
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RejectedWorkflow:
    name: str
    reasons: list[ValidationIssue]


@dataclass(slots=True)
class CoverageReport:
    covered_surface_areas: list[str] = field(default_factory=list)
    covered_interfaces: list[str] = field(default_factory=list)
    covered_services: list[str] = field(default_factory=list)
    covered_service_modes: list[str] = field(default_factory=list)
    covered_failure_modes: list[str] = field(default_factory=list)
    uncovered_surface_areas: list[str] = field(default_factory=list)
    uncovered_services: list[str] = field(default_factory=list)
    rejected_candidates: list[RejectedWorkflow] = field(default_factory=list)
    harness_results: list[HarnessDryRunResult] = field(default_factory=list)
    suite_narrative: str = ""
    catches: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    coverage_matrix: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""


@dataclass(slots=True)
class WorkflowGenerationRequest:
    docs: list[DocumentInput] = field(default_factory=list)
    mcp_server_url: str | None = None
    mcp_tools: list[dict[str, Any]] = field(default_factory=list)
    repo: RepositoryContext | None = None
    services: list[ServiceDependency] = field(default_factory=list)
    declared_secrets: list[str] = field(default_factory=list)
    egress_domains: list[str] = field(default_factory=list)
    live_service_approval: bool = False
    focus: str | None = None
    coverage: dict[str, Any] = field(default_factory=dict)
    planner: PlannerMode = "auto"
    planner_model: str | None = None
    repair_attempts: int = 1
    combine_rule_candidates: bool = True


@dataclass(slots=True)
class WorkflowGenerationResponse:
    surface_map: ProductSurfaceMap
    service_map: ServiceMap
    capability_graph: list[CapabilityChain]
    coverage_report: CoverageReport
    workflows: list[WorkflowDraft]


def to_plain(value: Any) -> Any:
    """Return JSON-serializable builtin containers for dataclass trees."""
    return asdict(value)
