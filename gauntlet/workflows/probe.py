"""Build product context from docs, MCP metadata, and repo hints."""

from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from .schema import Capability, DocumentInput, ProductSurfaceMap, RepositoryContext

_ACTION_RE = re.compile(
    r"\b(create|start|launch|open|read|list|get|search|find|update|delete|close|"
    r"send|post|draft|summari[sz]e|scrape|navigate|upload|download|run|execute|"
    r"approve|reject|refund|schedule|invite|comment|merge)\b",
    re.IGNORECASE,
)
_SECRET_RE = re.compile(r"\b[A-Z][A-Z0-9_]{5,}\b")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,4})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^\s{0,4}[-*]\s+(.+?)\s*$")


def build_surface_map(
    docs: list[DocumentInput],
    repo: RepositoryContext | None,
    mcp_tools: list[dict[str, Any]],
    declared_secrets: list[str],
) -> ProductSurfaceMap:
    interfaces = _detect_interfaces(docs, repo, mcp_tools)
    capabilities = _extract_doc_capabilities(docs, interfaces)
    capabilities.extend(_extract_mcp_capabilities(mcp_tools))

    if not capabilities:
        capabilities = [
            Capability(
                name="run documented product task",
                surface_area="core product",
                interfaces=interfaces or ["http"],
                inputs=["task"],
                outputs=["result"],
                evidence=["task result"],
                source="fallback",
            )
        ]

    capabilities = _dedupe_capabilities(capabilities)
    entities = _extract_entities(docs, capabilities)
    dangerous = _dangerous_operations(capabilities)
    secrets = sorted(set(declared_secrets) | set(_extract_secret_names(docs)))
    return ProductSurfaceMap(
        interfaces=interfaces or ["http"],
        capabilities=capabilities,
        entities=entities,
        dangerous_operations=dangerous,
        auth_requirements=secrets,
    )


def parse_docs(raw_docs: list[dict[str, Any]]) -> list[DocumentInput]:
    docs: list[DocumentInput] = []
    for idx, item in enumerate(raw_docs):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "")
        if not text.strip():
            continue
        title = str(item.get("title") or item.get("name") or f"doc-{idx + 1}")
        url = item.get("url")
        docs.append(DocumentInput(title=title, text=text[:200_000], url=str(url) if url else None))
    return docs


def parse_repo(raw_repo: dict[str, Any] | None) -> RepositoryContext | None:
    if not isinstance(raw_repo, dict):
        return None
    manifests = raw_repo.get("manifests") or []
    return RepositoryContext(
        runtime=str(raw_repo.get("runtime")) if raw_repo.get("runtime") else None,
        entrypoint=str(raw_repo.get("entrypoint")) if raw_repo.get("entrypoint") else None,
        manifests=[str(item) for item in manifests if item],
    )


def _detect_interfaces(
    docs: list[DocumentInput],
    repo: RepositoryContext | None,
    mcp_tools: list[dict[str, Any]],
) -> list[str]:
    haystack = "\n".join(doc.text.lower() for doc in docs)
    found: list[str] = []
    checks = [
        ("rest", ["rest", "http api", "openapi", "endpoint", "curl "]),
        ("sdk:python", ["python sdk", "pip install", "from ", "import "]),
        ("sdk:javascript", ["javascript sdk", "typescript", "npm install", "pnpm add"]),
        ("cli", [" cli", "command line", "$ ", "npx ", "uvx "]),
        ("mcp", ["mcp", "tools/list", "json-rpc"]),
        ("browser", ["browser", "web app", "dashboard", "click", "navigate"]),
    ]
    for interface, needles in checks:
        if any(needle in haystack for needle in needles):
            found.append(interface)
    if mcp_tools and "mcp" not in found:
        found.append("mcp")
    if repo:
        runtime = (repo.runtime or "").lower()
        if "python" in runtime and "sdk:python" not in found:
            found.append("sdk:python")
        if any(part in runtime for part in ("node", "javascript", "typescript")) and "sdk:javascript" not in found:
            found.append("sdk:javascript")
    return found


def _extract_doc_capabilities(docs: list[DocumentInput], interfaces: list[str]) -> list[Capability]:
    caps: list[Capability] = []
    current_section = "core product"
    for doc in docs:
        for raw_line in doc.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            heading = _HEADING_RE.match(line)
            if heading:
                current_section = _clean_phrase(heading.group(2))
                continue
            bullet = _BULLET_RE.match(line)
            candidate = bullet.group(1) if bullet else line
            if not _ACTION_RE.search(candidate):
                continue
            if len(candidate) > 180:
                candidate = candidate[:177].rstrip() + "..."
            name = _capability_name(candidate)
            caps.append(
                Capability(
                    name=name,
                    surface_area=current_section,
                    interfaces=_interfaces_for_text(candidate, interfaces),
                    inputs=_infer_inputs(candidate),
                    outputs=_infer_outputs(candidate),
                    side_effects=_infer_side_effects(candidate),
                    prerequisites=sorted(_SECRET_RE.findall(candidate)),
                    evidence=_infer_evidence(candidate),
                    source=doc.title,
                )
            )
            if len(caps) >= 36:
                break
    return caps


def _extract_mcp_capabilities(mcp_tools: list[dict[str, Any]]) -> list[Capability]:
    caps: list[Capability] = []
    for tool in mcp_tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or tool.get("id") or "").strip()
        if not name:
            continue
        description = str(tool.get("description") or "")
        caps.append(
            Capability(
                name=_clean_phrase(name.replace("_", " ")),
                surface_area="mcp tools",
                interfaces=["mcp"],
                inputs=_schema_keys(tool.get("inputSchema") or tool.get("input_schema")),
                outputs=["tool result"],
                side_effects=_infer_side_effects(f"{name} {description}"),
                evidence=["MCP tool response"],
                source="mcp",
            )
        )
    return caps


def _dedupe_capabilities(capabilities: list[Capability]) -> list[Capability]:
    seen: OrderedDict[str, Capability] = OrderedDict()
    for cap in capabilities:
        key = f"{cap.surface_area.lower()}::{cap.name.lower()}"
        if key not in seen:
            seen[key] = cap
    return list(seen.values())[:24]


def _extract_entities(docs: list[DocumentInput], capabilities: list[Capability]) -> list[str]:
    known = [
        "session",
        "profile",
        "workflow",
        "run",
        "artifact",
        "message",
        "thread",
        "customer",
        "order",
        "payment",
        "refund",
        "ticket",
        "issue",
        "pull request",
        "calendar event",
        "file",
    ]
    haystack = "\n".join(doc.text.lower() for doc in docs) + " " + " ".join(cap.name.lower() for cap in capabilities)
    found = [entity for entity in known if entity in haystack]
    return found or ["task", "result"]


def _dangerous_operations(capabilities: list[Capability]) -> list[str]:
    dangerous_terms = ("delete", "charge", "refund", "send", "post", "merge", "approve", "reject", "invite")
    found = sorted({term for cap in capabilities for term in dangerous_terms if term in cap.name.lower()})
    return found


def _extract_secret_names(docs: list[DocumentInput]) -> list[str]:
    found: set[str] = set()
    for doc in docs:
        for name in _SECRET_RE.findall(doc.text):
            if name.endswith("_KEY") or name.endswith("_TOKEN") or name.endswith("_SECRET"):
                found.add(name)
    return sorted(found)


def _interfaces_for_text(text: str, interfaces: list[str]) -> list[str]:
    lower = text.lower()
    picked = []
    for interface in interfaces:
        if interface == "rest" and any(word in lower for word in ("api", "endpoint", "http", "curl")):
            picked.append(interface)
        elif interface == "cli" and any(word in lower for word in ("cli", "command", "npx", "$ ")):
            picked.append(interface)
        elif interface == "mcp" and "mcp" in lower:
            picked.append(interface)
        elif interface == "browser" and any(word in lower for word in ("browser", "click", "dashboard", "navigate")):
            picked.append(interface)
        elif interface.startswith("sdk") and any(word in lower for word in ("sdk", "python", "javascript", "typescript", "import")):
            picked.append(interface)
    return picked or interfaces[:2] or ["http"]


def _capability_name(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return _clean_phrase(text)


def _clean_phrase(text: str) -> str:
    text = re.sub(r"[*_`#>\[\](){}]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return text[:96] or "core product"


def _infer_inputs(text: str) -> list[str]:
    lower = text.lower()
    inputs = []
    for name in ("url", "file", "message", "email", "order id", "customer id", "session id", "profile id", "prompt"):
        if name in lower:
            inputs.append(name)
    return inputs or ["task input"]


def _infer_outputs(text: str) -> list[str]:
    lower = text.lower()
    outputs = []
    for name in ("session id", "screenshot", "summary", "draft", "message", "artifact", "result", "refund", "report"):
        if name in lower:
            outputs.append(name)
    return outputs or ["observable result"]


def _infer_side_effects(text: str) -> list[str]:
    lower = text.lower()
    side_effects = []
    mapping = {
        "create": "creates_state",
        "start": "creates_state",
        "launch": "creates_state",
        "update": "updates_state",
        "delete": "deletes_state",
        "send": "sends_external_message",
        "post": "posts_message",
        "draft": "creates_draft",
        "refund": "creates_refund",
        "merge": "merges_change",
        "approve": "approves_change",
    }
    for needle, value in mapping.items():
        if needle in lower:
            side_effects.append(value)
    return sorted(set(side_effects))


def _infer_evidence(text: str) -> list[str]:
    lower = text.lower()
    evidence = ["transcript"]
    if any(word in lower for word in ("create", "update", "delete", "post", "send", "draft", "refund")):
        evidence.append("service or API state")
    if any(word in lower for word in ("screenshot", "artifact", "download", "file", "report")):
        evidence.append("artifact")
    return evidence


def _schema_keys(schema: Any) -> list[str]:
    if not isinstance(schema, dict):
        return ["tool input"]
    props = schema.get("properties")
    if isinstance(props, dict):
        return [str(key) for key in props.keys()]
    return ["tool input"]
