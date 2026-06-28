"""Normalize service clone/twin declarations for generation."""

from __future__ import annotations

from typing import Any

from .schema import EgressRule, ServiceDependency, ServiceMap

_KNOWN_SERVICE_DEFAULTS: dict[str, dict[str, list[str]]] = {
    "slack": {
        "capabilities": ["read channel", "post message", "read thread"],
        "observable_state": ["messages", "threads", "reactions"],
        "allowed_side_effects": ["post_message"],
    },
    "gmail": {
        "capabilities": ["search inbox", "read message", "draft reply"],
        "observable_state": ["threads", "messages", "drafts"],
        "allowed_side_effects": ["create_draft"],
    },
    "stripe": {
        "capabilities": ["lookup customer", "lookup payment", "create refund"],
        "observable_state": ["customers", "payments", "refunds"],
        "allowed_side_effects": ["create_refund"],
        "forbidden_side_effects": ["capture_live_payment"],
    },
    "github": {
        "capabilities": ["read issue", "comment on issue", "inspect pull request"],
        "observable_state": ["issues", "comments", "pull requests"],
        "allowed_side_effects": ["post_comment"],
    },
    "jira": {
        "capabilities": ["read ticket", "update ticket", "transition ticket"],
        "observable_state": ["tickets", "comments", "status"],
        "allowed_side_effects": ["update_ticket"],
    },
    "calendar": {
        "capabilities": ["read availability", "create event", "update event"],
        "observable_state": ["events", "attendees"],
        "allowed_side_effects": ["create_event"],
    },
}


def build_service_map(raw_services: list[dict[str, Any]] | list[ServiceDependency]) -> ServiceMap:
    services: list[ServiceDependency] = []
    seen: set[str] = set()
    for raw in raw_services:
        service = raw if isinstance(raw, ServiceDependency) else parse_service(raw)
        key = service.name.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        services.append(_with_defaults(service))
    return ServiceMap(services=services)


def parse_service(raw: dict[str, Any]) -> ServiceDependency:
    name = str(raw.get("name") or raw.get("service") or "").strip().lower()
    mode = str(raw.get("mode") or "twin").lower()
    if mode not in {"twin", "live", "record"}:
        mode = "twin"
    return ServiceDependency(
        name=name,
        mode=mode,  # type: ignore[arg-type]
        capabilities=_string_list(raw.get("capabilities")),
        seed_data=_string_list(raw.get("seed_data")),
        allowed_side_effects=_string_list(raw.get("allowed_side_effects")),
        forbidden_side_effects=_string_list(raw.get("forbidden_side_effects")),
        observable_state=_string_list(raw.get("observable_state")),
        cleanup_required=bool(raw.get("cleanup_required", False)),
        domain=str(raw.get("domain")) if raw.get("domain") else None,
        version=str(raw.get("version")) if raw.get("version") else None,
        live_approved=bool(raw.get("live_approved", False)),
    )


def egress_for_services(services: list[ServiceDependency]) -> list[EgressRule]:
    return [
        EgressRule(
            domain=service.domain or f"{service.name}.local",
            mode=service.mode,
            service=service.name,
            approved=service.live_approved,
        )
        for service in services
    ]


def _with_defaults(service: ServiceDependency) -> ServiceDependency:
    defaults = _KNOWN_SERVICE_DEFAULTS.get(service.name, {})
    service.capabilities = service.capabilities or list(defaults.get("capabilities", [])) or [
        f"read {service.name} records",
        f"write {service.name} records",
    ]
    service.observable_state = service.observable_state or list(defaults.get("observable_state", [])) or ["records"]
    service.allowed_side_effects = service.allowed_side_effects or list(defaults.get("allowed_side_effects", []))
    service.forbidden_side_effects = service.forbidden_side_effects or list(defaults.get("forbidden_side_effects", []))
    service.domain = service.domain or f"{service.name}.local"
    return service


def _string_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                ident = item.get("id") or item.get("ref") or item.get("name") or item.get("description")
                if ident:
                    result.append(str(ident))
            elif item:
                result.append(str(item))
        return result
    return [str(value)]
