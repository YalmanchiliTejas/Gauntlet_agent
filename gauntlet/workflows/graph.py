"""Capability graph construction for visible workflow derivation."""

from __future__ import annotations

from .schema import CapabilityChain, ProductSurfaceMap, ServiceDependency


def build_capability_graph(
    surface_map: ProductSurfaceMap,
    services: list[ServiceDependency],
) -> list[CapabilityChain]:
    chains: list[CapabilityChain] = []
    for cap in surface_map.capabilities[:8]:
        services_for_chain = _services_for_capability(cap.name, services)
        steps = ["prepare inputs", cap.name]
        if services_for_chain:
            steps.extend(f"{service.name}: {service.capabilities[0]}" for service in services_for_chain if service.capabilities)
            steps.append("verify service or twin state")
        else:
            steps.append("capture product output")
        risk = "high" if services_for_chain and (cap.side_effects or len(services_for_chain) > 1) else "medium"
        chains.append(
            CapabilityChain(
                name=f"{cap.surface_area}: {cap.name}",
                steps=steps,
                services=[service.name for service in services_for_chain],
                interfaces=cap.interfaces,
                risk_level=risk,
                reason="Derived from documented product capability and declared service dependencies.",
            )
        )

    if len(services) >= 2 and surface_map.capabilities:
        core = surface_map.capabilities[0]
        chains.insert(
            0,
            CapabilityChain(
                name=f"multi-service {core.surface_area}",
                steps=[
                    f"use product capability: {core.name}",
                    *[f"{service.name}: {', '.join(service.capabilities[:2])}" for service in services[:4]],
                    "verify cross-service state and summarize evidence",
                ],
                services=[service.name for service in services[:4]],
                interfaces=core.interfaces,
                risk_level="high",
                reason="Multi-service state chaining is a core risk for agent workflows.",
            ),
        )
    return chains[:12]


def _services_for_capability(name: str, services: list[ServiceDependency]) -> list[ServiceDependency]:
    lower = name.lower()
    matched = [service for service in services if service.name in lower]
    if matched:
        return matched
    action_terms = set(lower.split())
    inferred = []
    for service in services:
        service_terms = " ".join(service.capabilities).lower().split()
        if action_terms.intersection(service_terms):
            inferred.append(service)
    return inferred[:2]
