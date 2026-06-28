"""LLM-backed workflow planner with strict typed parsing.

The LLM is a candidate generator only. Deterministic validation and harness
scoring remain the gate before workflows reach the API response.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import asdict
from typing import Any, Callable

from .schema import (
    EgressRule,
    ProductSurfaceMap,
    SeedDataRequirement,
    ServiceDependency,
    ServiceMap,
    SuccessCondition,
    WorkflowDraft,
    WorkflowGenerationRequest,
)
from .service_map import egress_for_services

PromptSender = Callable[[str], str]

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_MAX_DOC_CHARS = 18_000


class LLMPlanner:
    name = "llm"

    def __init__(self, sender: PromptSender | None = None, model: str | None = None) -> None:
        self.sender = sender or _send_prompt
        self.model = model

    def available(self) -> bool:
        return bool(
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GAUNTLET_PLANNER_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )

    def generate_candidates(
        self,
        request: WorkflowGenerationRequest,
        surface_map: ProductSurfaceMap,
        service_map: ServiceMap,
    ) -> list[WorkflowDraft]:
        prompt = _build_generation_prompt(request, surface_map, service_map)
        raw = self.sender(prompt)
        data = _extract_json_object(raw)
        return parse_workflow_candidates(data, surface_map, service_map)

    def repair_candidate(
        self,
        workflow: WorkflowDraft,
        validation_errors: list[str],
        request: WorkflowGenerationRequest,
        surface_map: ProductSurfaceMap,
        service_map: ServiceMap,
    ) -> WorkflowDraft | None:
        prompt = _build_repair_prompt(workflow, validation_errors, request, surface_map, service_map)
        try:
            raw = self.sender(prompt)
            data = _extract_json_object(raw)
            workflows = parse_workflow_candidates(data, surface_map, service_map)
        except Exception:
            return None
        return workflows[0] if workflows else None


def parse_workflow_candidates(
    data: dict[str, Any],
    surface_map: ProductSurfaceMap,
    service_map: ServiceMap,
) -> list[WorkflowDraft]:
    items = data.get("workflows") or []
    if isinstance(data.get("workflow"), dict):
        items = [data["workflow"]]
    if not isinstance(items, list):
        return []

    services_by_name = {service.name: service for service in service_map.services}
    caps_by_name = {cap.name: cap for cap in surface_map.capabilities}
    workflows: list[WorkflowDraft] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        services = _parse_services(item.get("services"), services_by_name)
        product_caps = _parse_product_capabilities(item.get("product_capabilities"), caps_by_name)
        if not product_caps and surface_map.capabilities:
            product_caps = [surface_map.capabilities[0].name]
        required_secrets = _string_list(item.get("required_secrets"))
        for cap_name in product_caps:
            cap = caps_by_name.get(cap_name)
            if cap:
                required_secrets.extend(cap.prerequisites)
        workflows.append(
            WorkflowDraft(
                name=str(item.get("name") or "Generated workflow").strip(),
                description=str(item.get("description") or "Generated workflow candidate.").strip(),
                audience=_literal(item.get("audience"), {"agent_builder", "infrastructure_builder"}, "agent_builder"),
                workflow_type=_literal(item.get("workflow_type"), {"agent_under_test", "platform_under_test"}, "agent_under_test"),
                surface_area=str(item.get("surface_area") or _surface_for_cap(product_caps, caps_by_name) or "core product"),
                product_capabilities=product_caps,
                services=services,
                task_prompt=str(item.get("task_prompt") or "").strip(),
                required_secrets=sorted(set(required_secrets)),
                egress_policy=_parse_egress(item.get("egress_policy"), services),
                seed_data=_parse_seed_data(item.get("seed_data"), services),
                expected_state_transitions=_string_list(item.get("expected_state_transitions")),
                success_conditions=_parse_success_conditions(item.get("success_conditions")),
                rubric=_string_list(item.get("rubric")),
                failure_modes_tested=_string_list(item.get("failure_modes_tested")),
                difficulty=_literal(item.get("difficulty"), {"smoke", "core", "hard", "adversarial", "recovery"}, "core"),
                cleanup_required=bool(item.get("cleanup_required", any(service.cleanup_required for service in services))),
                target_interfaces=_string_list(item.get("target_interfaces")),
                selection_reason=str(item.get("selection_reason") or "Generated by LLM planner and awaiting validation."),
            )
        )
    return workflows


def _build_generation_prompt(
    request: WorkflowGenerationRequest,
    surface_map: ProductSurfaceMap,
    service_map: ServiceMap,
) -> str:
    count = int(request.coverage.get("candidate_count") or max(int(request.coverage.get("count") or 5) * 3, 10))
    docs_excerpt = "\n\n".join(f"# {doc.title}\n{doc.text[:6000]}" for doc in request.docs)
    docs_excerpt = docs_excerpt[:_MAX_DOC_CHARS]
    context = {
        "surface_map": asdict(surface_map),
        "service_map": asdict(service_map),
        "coverage": request.coverage,
        "declared_secrets": request.declared_secrets,
        "egress_domains": request.egress_domains,
        "docs_excerpt": docs_excerpt,
    }
    return (
        "You design high-quality executable agent test workflows for Gauntlet.\n"
        "Generate candidate workflows only from the supplied product docs, surface map, and service/twin map.\n"
        "Quality bar:\n"
        "- Each task_prompt must be a realistic user request, not meta commentary.\n"
        "- Be specific about the interface: CLI, Python SDK, JavaScript SDK, REST, MCP, or browser.\n"
        "- Use self-contained literal inputs or resources created in the same task.\n"
        "- Never invent fake IDs, placeholder resources, secret values, or undocumented capabilities.\n"
        "- Include concrete success_conditions with evidence types: transcript, artifact, service_state, twin_state, api_response.\n"
        "- Include service/twin routing, seed data, egress policy, expected state transitions, rubrics, and failure modes where relevant.\n"
        "- Prefer end-to-end chains like create session -> connect -> navigate -> capture artifact -> release/verify cleanup.\n"
        "- Cover different surfaces, interfaces, task shapes, and failure modes. Avoid duplicates.\n"
        "Return JSON only with this shape: {\"workflows\": [...]}.\n\n"
        "Each workflow object fields:\n"
        "name, description, audience, workflow_type, surface_area, product_capabilities, target_interfaces, services,\n"
        "task_prompt, required_secrets, egress_policy, seed_data, expected_state_transitions,\n"
        "success_conditions, rubric, failure_modes_tested, difficulty, cleanup_required, selection_reason.\n\n"
        "Strict field requirements:\n"
        "- target_interfaces must use values from: cli, rest, sdk:python, sdk:javascript, mcp, browser.\n"
        "- task_prompt must be at least 20 words and must name the target interface explicitly.\n"
        "- success_conditions must be a list of objects, not strings. Each object must be exactly "
        "{\"description\": \"specific check\", \"evidence\": \"transcript|artifact|service_state|twin_state|api_response\"}.\n"
        "- At least one success condition must use artifact, service_state, twin_state, or api_response evidence.\n"
        "- Avoid vague words in success conditions: correctly, successfully, properly, appropriate, as needed.\n"
        "- If the workflow creates a session, the task and success conditions must verify cleanup/release.\n"
        "- If no service twins are declared, services, egress_policy, and seed_data should be empty lists.\n\n"
        "Example success_conditions:\n"
        "[\n"
        "  {\"description\": \"The trace shows the Python SDK created a Steel session before browser navigation.\", \"evidence\": \"transcript\"},\n"
        "  {\"description\": \"A screenshot or page title artifact from https://example.com was captured.\", \"evidence\": \"artifact\"},\n"
        "  {\"description\": \"The final trace includes a release or cleanup call for the created session.\", \"evidence\": \"api_response\"}\n"
        "]\n\n"
        f"Generate {count} candidate workflows.\n\n"
        f"CONTEXT JSON:\n{json.dumps(context, indent=2)[:60_000]}"
    )


def _build_repair_prompt(
    workflow: WorkflowDraft,
    validation_errors: list[str],
    request: WorkflowGenerationRequest,
    surface_map: ProductSurfaceMap,
    service_map: ServiceMap,
) -> str:
    return (
        "Repair this generated workflow so it passes Gauntlet's deterministic validator.\n"
        "Do not weaken the task. Remove fake IDs, undeclared egress, unknown services, vague criteria, or impossible prerequisites.\n"
        "Return JSON only as {\"workflows\": [<one repaired workflow>]}.\n\n"
        f"VALIDATION ERRORS:\n{json.dumps(validation_errors, indent=2)}\n\n"
        f"WORKFLOW:\n{json.dumps(asdict(workflow), indent=2)}\n\n"
        f"SURFACE MAP:\n{json.dumps(asdict(surface_map), indent=2)[:20_000]}\n\n"
        f"SERVICE MAP:\n{json.dumps(asdict(service_map), indent=2)}\n\n"
        f"DECLARED SECRETS:\n{json.dumps(request.declared_secrets)}"
    )


def _send_prompt(prompt: str) -> str:
    provider = os.environ.get("GAUNTLET_PLANNER_PROVIDER", "").strip().lower()
    if provider == "gemini" or (not provider and os.environ.get("GEMINI_API_KEY")):
        return _send_gemini_prompt(prompt)
    return _send_openai_compatible_prompt(prompt)


def _send_gemini_prompt(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for Gemini workflow planning")
    model = os.environ.get("GAUNTLET_PLANNER_MODEL", "gemini-2.5-pro")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = json.dumps(
        {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "You are a precise workflow planner. Output valid JSON only.\n\n"
                                + prompt
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.loads(response.read().decode())
    try:
        return "".join(
            part.get("text", "")
            for candidate in payload.get("candidates", [])
            for part in candidate.get("content", {}).get("parts", [])
        )
    except AttributeError as exc:
        raise RuntimeError("Gemini planner response did not contain text output") from exc


def _send_openai_compatible_prompt(prompt: str) -> str:
    api_key = os.environ.get("GAUNTLET_PLANNER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY, GAUNTLET_PLANNER_API_KEY, or OPENAI_API_KEY is required for LLM planner")
    base_url = os.environ.get("GAUNTLET_PLANNER_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("GAUNTLET_PLANNER_MODEL", "gpt-4.1")
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a precise workflow planner. Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    ).encode()
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={"authorization": f"Bearer {api_key}", "content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode())
    return payload["choices"][0]["message"]["content"]


def _extract_json_object(text: str) -> dict[str, Any]:
    match = _JSON_BLOCK_RE.search(text)
    if match:
        candidate = match.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Planner response did not contain a JSON object")
        candidate = text[start : end + 1]
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("Planner JSON root must be an object")
    return data


def _parse_services(raw: Any, services_by_name: dict[str, ServiceDependency]) -> list[ServiceDependency]:
    names: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                name = item.get("name") or item.get("service")
            else:
                name = item
            if name:
                names.append(str(name).lower())
    return [services_by_name[name] for name in names if name in services_by_name]


def _parse_product_capabilities(raw: Any, caps_by_name: dict[str, Any]) -> list[str]:
    values = _string_list(raw)
    return [value for value in values if value in caps_by_name]


def _parse_egress(raw: Any, services: list[ServiceDependency]) -> list[EgressRule]:
    if not isinstance(raw, list):
        return egress_for_services(services)
    rules: list[EgressRule] = []
    service_domains = {service.domain or f"{service.name}.local": service for service in services}
    for item in raw:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "")
        service = service_domains.get(domain)
        if not domain:
            continue
        mode = str(item.get("mode") or (service.mode if service else "twin"))
        if mode not in {"twin", "live", "record"}:
            mode = "twin"
        rules.append(EgressRule(domain=domain, mode=mode, service=str(item.get("service")) if item.get("service") else (service.name if service else None), approved=bool(item.get("approved", False))))
    return rules or egress_for_services(services)


def _parse_seed_data(raw: Any, services: list[ServiceDependency]) -> list[SeedDataRequirement]:
    seed: list[SeedDataRequirement] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                service = str(item.get("service") or "")
                ref = str(item.get("ref") or item.get("id") or "")
                if service and ref:
                    seed.append(SeedDataRequirement(service=service.lower(), ref=ref, description=str(item.get("description") or "")))
            elif services and item:
                seed.append(SeedDataRequirement(service=services[0].name, ref=str(item), description="Planner-provided seed data."))
    if not seed:
        for service in services:
            for value in (service.seed_data or [])[:3]:
                seed.append(SeedDataRequirement(service=service.name, ref=value, description=f"Seed record for {service.name}."))
    return seed


def _parse_success_conditions(raw: Any) -> list[SuccessCondition]:
    conditions: list[SuccessCondition] = []
    if not isinstance(raw, list):
        return conditions
    valid = {"transcript", "artifact", "service_state", "twin_state", "api_response"}
    for item in raw:
        if isinstance(item, dict):
            description = str(item.get("description") or item.get("condition") or "").strip()
            evidence = str(item.get("evidence") or "transcript")
        else:
            description = str(item).strip()
            evidence = "transcript"
        if description:
            if evidence not in valid:
                evidence = "transcript"
            conditions.append(SuccessCondition(description=description, evidence=evidence))  # type: ignore[arg-type]
    return conditions


def _surface_for_cap(capabilities: list[str], caps_by_name: dict[str, Any]) -> str | None:
    for name in capabilities:
        cap = caps_by_name.get(name)
        if cap:
            return cap.surface_area
    return None


def _literal(value: Any, allowed: set[str], fallback: str):
    text = str(value) if value is not None else fallback
    return text if text in allowed else fallback


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("description") or item.get("name") or item.get("value")
                if text:
                    result.append(str(text))
            elif item:
                result.append(str(item))
        return result
    return [str(value)]
