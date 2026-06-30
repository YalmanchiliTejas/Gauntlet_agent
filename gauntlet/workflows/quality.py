"""Workflow quality normalization before validation and scoring."""

from __future__ import annotations

from .schema import WorkflowDraft


def normalize_workflow_quality(workflow: WorkflowDraft) -> WorkflowDraft:
    """Fill quality gaps that are safe to repair deterministically.

    This does not invent new capabilities or services. It only expands judgeable
    rubric criteria and aligns generic wording with fields already present on the
    workflow.
    """
    workflow.rubric = _normalize_rubric(workflow)
    workflow.quality_badges = _normalize_badges(workflow)
    workflow.expected_artifacts = _normalize_expected_artifacts(workflow)
    workflow.run_readiness = _normalize_run_readiness(workflow)
    return workflow


def _normalize_rubric(workflow: WorkflowDraft) -> list[str]:
    existing = [item.strip() for item in workflow.rubric if item and item.strip()]
    rubric: list[str] = []
    for item in existing:
        if item not in rubric:
            rubric.append(item)

    additions = [
        "The agent actually completed the requested workflow end-to-end; describing a plan or asking for missing IDs does not pass.",
        "Every identifier used by the agent came from the prompt, declared seed data, or an observed response created earlier in the same run.",
        "The execution used the workflow's target interface instead of satisfying the task through an unintended surface.",
        "The final response cites concrete transcript, API response, artifact, service-state, or twin-state evidence for the outcome.",
    ]
    if workflow.cleanup_required:
        additions.append("Any session or resource created during the workflow was explicitly cleaned up or released before the final answer.")
    if workflow.services:
        additions.append("The workflow used only declared service routes and respected the configured service modes.")

    for item in additions:
        if len(rubric) >= 5:
            break
        if item not in rubric:
            rubric.append(item)
    return rubric


def _normalize_badges(workflow: WorkflowDraft) -> list[str]:
    badges = list(dict.fromkeys(workflow.quality_badges))
    evidence = {condition.evidence for condition in workflow.success_conditions}
    text = " ".join([workflow.name, workflow.task_prompt, workflow.surface_area, " ".join(workflow.failure_modes_tested)]).lower()
    inferred = []
    if workflow.cleanup_required:
        inferred.append("Cleanup required")
    if "artifact" in evidence:
        inferred.append("Artifact-backed")
    if "trace" in text:
        inferred.append("Trace-backed")
    if "profile" in text or "auth" in text:
        inferred.append("Auth-context")
    if "scrape" in text or "cli" in workflow.target_interfaces or "rest" in workflow.target_interfaces:
        inferred.append("Interface-choice")
    if any(mode in text for mode in ("false success", "identifier", "stale", "wrong interface")):
        inferred.append("False-success resistant")
    for badge in inferred:
        if badge not in badges:
            badges.append(badge)
    return badges


def _normalize_expected_artifacts(workflow: WorkflowDraft) -> list[str]:
    artifacts = list(dict.fromkeys(workflow.expected_artifacts))
    text = " ".join([workflow.task_prompt] + [condition.description for condition in workflow.success_conditions]).lower()
    inferred = []
    if "session id" in text:
        inferred.append("session_id")
    if "profile id" in text:
        inferred.append("profile_id")
    if "screenshot" in text:
        inferred.append("screenshot")
    if "title" in text:
        inferred.append("page_title")
    if "file" in text:
        inferred.append("file_artifact")
    if "trace" in text or "event" in text:
        inferred.append("trace_events")
    if "release" in text or "cleanup" in text:
        inferred.append("cleanup_response")
    for artifact in inferred:
        if artifact not in artifacts:
            artifacts.append(artifact)
    return artifacts


def _normalize_run_readiness(workflow: WorkflowDraft) -> dict:
    readiness = dict(workflow.run_readiness)
    readiness.setdefault("ready", True)
    readiness.setdefault("required_secrets", workflow.required_secrets)
    readiness.setdefault("routes", [f"{rule.service or rule.domain}:{rule.mode}" for rule in workflow.egress_policy])
    readiness.setdefault("blockers", [])
    return readiness
