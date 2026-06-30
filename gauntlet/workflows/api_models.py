"""FastAPI request models for workflow generation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DocumentPayload(BaseModel):
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    url: str | None = None


class RepoPayload(BaseModel):
    runtime: str | None = None
    entrypoint: str | None = None
    manifests: list[str] = Field(default_factory=list)


class ServicePayload(BaseModel):
    name: str = Field(min_length=1)
    mode: Literal["twin", "live", "record"] = "twin"
    version: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    seed_data: list[Any] = Field(default_factory=list)
    allowed_side_effects: list[str] = Field(default_factory=list)
    forbidden_side_effects: list[str] = Field(default_factory=list)
    observable_state: list[str] = Field(default_factory=list)
    cleanup_required: bool = False
    domain: str | None = None
    live_approved: bool = False


class CoveragePayload(BaseModel):
    count: int = Field(default=5, ge=1, le=12)
    include_multi_service: bool = True
    include_recovery: bool = True
    include_adversarial: bool = True


class WorkflowGeneratePayload(BaseModel):
    docs: list[DocumentPayload] = Field(default_factory=list)
    mcp_server_url: str | None = None
    mcp_tools: list[dict[str, Any]] = Field(default_factory=list)
    repo: RepoPayload | None = None
    services: list[ServicePayload] = Field(default_factory=list)
    declared_secrets: list[str] = Field(default_factory=list)
    egress_domains: list[str] = Field(default_factory=list)
    live_service_approval: bool = False
    coverage: CoveragePayload = Field(default_factory=CoveragePayload)
    planner: Literal["auto", "rules", "llm"] = "auto"
    planner_model: str | None = None
    repair_attempts: int = Field(default=1, ge=0, le=3)
    combine_rule_candidates: bool = True


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dump()
    return model.dict()
