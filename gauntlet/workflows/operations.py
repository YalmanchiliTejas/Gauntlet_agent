"""Extract concrete documented operations from product docs.

The rules planner uses these operations to produce executable prompts without
hardcoding any product-specific branches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schema import DocumentInput


@dataclass(slots=True)
class DocumentedOperation:
    label: str
    interface: str
    kind: str
    surface_area: str
    source: str
    context: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)


_HEADING_RE = re.compile(r"^\s{0,3}(#{1,4})\s+(.+?)\s*$")
_CODE_SPAN_RE = re.compile(r"`([^`\n]{2,220})`")
_HTTP_RE = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE)\s+((?:https?://[^\s`|)]+)|(?:/[A-Za-z0-9_{}:./-]+))",
    re.IGNORECASE,
)
_URL_PATH_RE = re.compile(r"https?://[A-Za-z0-9.-]+(/[A-Za-z0-9_{}:./-]+)")
_SDK_CALL_RE = re.compile(
    r"\b(?:await\s+)?(?:[A-Za-z_][\w]*\.)+[A-Za-z_][\w]*\([^`\n)]*\)",
)
_CLI_RE = re.compile(r"^(?:[A-Za-z][\w-]*|npx|uvx|pnpm|npm|yarn|bun)(?:\s+[-./:@A-Za-z0-9_{}=]+){1,12}$")
_PROSE_ACTION_RE = re.compile(
    r"\b(create|start|launch|open|read|list|get|search|find|update|delete|close|"
    r"send|post|draft|summari[sz]e|scrape|navigate|upload|download|run|execute|"
    r"approve|reject|refund|schedule|invite|comment|merge)\b",
    re.IGNORECASE,
)


def extract_documented_operations(docs: list[DocumentInput]) -> list[DocumentedOperation]:
    operations: list[DocumentedOperation] = []
    seen: set[tuple[str, str, str]] = set()
    for doc in docs:
        current_section = "documentation"
        for raw_line in doc.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            heading = _HEADING_RE.match(line)
            if heading:
                current_section = _clean(heading.group(2))
                continue
            for operation in _operations_from_line(line, current_section, doc.title):
                key = (operation.label.lower(), operation.interface, operation.kind)
                if key in seen:
                    continue
                seen.add(key)
                operations.append(operation)
                if len(operations) >= 5000:
                    return operations
    return operations


def operations_for_kind(
    operations: list[DocumentedOperation],
    kind: str,
    *,
    preferred_terms: tuple[str, ...] = (),
    limit: int = 4,
) -> list[DocumentedOperation]:
    matches = [operation for operation in operations if operation.kind == kind]
    if not matches and kind == "retrieval":
        matches = [operation for operation in operations if operation.kind == "read"]
    label_matches = [
        operation
        for operation in matches
        if any(_term_matches(operation.label, term) for term in preferred_terms)
    ]
    if label_matches:
        matches = label_matches
    if not matches:
        matches = [
            operation
            for operation in operations
            if any(term in _operation_blob(operation) for term in preferred_terms)
        ]
    return sorted(matches, key=lambda operation: _score_operation(operation, preferred_terms), reverse=True)[:limit]


def format_operations(operations: list[DocumentedOperation]) -> str:
    if not operations:
        return "the documented product interface"
    return ", ".join(_format_operation(operation) for operation in operations)


def operation_labels(operations: list[DocumentedOperation]) -> list[str]:
    return [operation.label for operation in operations]


def operations_matching_labels(
    operations: list[DocumentedOperation],
    terms: tuple[str, ...],
    *,
    kinds: tuple[str, ...] = (),
    limit: int = 4,
) -> list[DocumentedOperation]:
    matches = [
        operation
        for operation in operations
        if (not kinds or operation.kind in kinds)
        and any(_term_matches(operation.label, term) for term in terms)
    ]
    return sorted(matches, key=lambda operation: _score_operation(operation, terms), reverse=True)[:limit]


def _operations_from_line(line: str, section: str, source: str) -> list[DocumentedOperation]:
    found: list[DocumentedOperation] = []
    spans = [match.group(1).strip() for match in _CODE_SPAN_RE.finditer(line)]
    candidates = spans + [match.group(0).strip() for match in _SDK_CALL_RE.finditer(line)]
    for method, target in _HTTP_RE.findall(line):
        if _is_doc_path(target):
            continue
        found.append(_make_operation(f"{method.upper()} {target}", "rest", section, source, line))
    for path in _URL_PATH_RE.findall(line):
        if _is_doc_path(path) or not _is_api_path(path):
            continue
        if any(operation.label.endswith(path) or path in operation.label for operation in found):
            continue
        found.append(_make_operation(path, "rest", section, source, line))
    for candidate in candidates:
        normalized = _normalize_candidate(candidate)
        if not normalized:
            continue
        if normalized.startswith("/") and (_is_doc_path(normalized) or not _is_api_path(normalized)):
            continue
        if _is_http_operation(normalized):
            for method, target in _HTTP_RE.findall(normalized):
                found.append(_make_operation(f"{method.upper()} {target}", "rest", section, source, line))
            continue
        if _looks_like_sdk_call(normalized):
            found.append(_make_operation(normalized, _sdk_interface(normalized, line), section, source, line))
            continue
        if _looks_like_cli(normalized):
            interface = "rest" if normalized.startswith("curl ") else "cli"
            found.append(_make_operation(normalized, interface, section, source, line))
    if found and not any(operation.kind == "cleanup" for operation in found):
        cleanup_phrase = _action_phrase(line, ("release", "close", "cleanup", "delete", "terminate", "stop"))
        if cleanup_phrase:
            found.append(_make_operation(cleanup_phrase, _prose_interface(line, section), section, source, line))
    if not found and _looks_like_prose_operation(line):
        found.append(_make_operation(_clean_prose_operation(line), _prose_interface(line, section), section, source, line))
    return found


def _make_operation(label: str, interface: str, section: str, source: str, context: str) -> DocumentedOperation:
    cleaned = _clean_operation(label)
    return DocumentedOperation(
        label=cleaned,
        interface=interface,
        kind=_infer_kind(cleaned),
        surface_area=section,
        source=source,
        context=_clean(context)[:240],
        inputs=_infer_inputs(cleaned, context),
        outputs=_infer_outputs(cleaned, context),
    )


def _infer_kind(text: str) -> str:
    lower = text.lower()
    if any(term in lower for term in ("event", "trace", "timeline", "log", "audit", "history")):
        return "observability"
    if any(term in lower for term in ("upload", "download", "file", "attachment", "archive", "zip")):
        return "artifact"
    if any(term in lower for term in ("profile", "context", "cookie", "credential", "auth", "identity")):
        return "context"
    if any(term in lower for term in ("release", "delete", "close", "cleanup", "terminate", "stop")):
        return "cleanup"
    if any(term in lower for term in ("create", "start", "launch", "run", "open")):
        return "lifecycle"
    if any(term in lower for term in ("scrape", "search", "list", "get", "read", "fetch", "export")):
        return "retrieval"
    return "read"


def _infer_inputs(label: str, context: str) -> list[str]:
    lower = f"{label} {context}".lower()
    values = []
    for item in ("url", "session id", "profile id", "file", "path", "query", "title", "invoice id", "issue id"):
        if item in lower:
            values.append(item)
    return values or ["documented input"]


def _infer_outputs(label: str, context: str) -> list[str]:
    lower = f"{label} {context}".lower()
    values = []
    for item in ("id", "status", "events", "file", "content", "response", "artifact", "screenshot", "title"):
        if item in lower:
            values.append(item)
    return values or ["operation response"]


def _score_operation(operation: DocumentedOperation, preferred_terms: tuple[str, ...]) -> int:
    blob = _operation_blob(operation)
    label = operation.label.lower()
    score = 0
    score -= 100 if _is_doc_path(operation.label) else 0
    score += 60 * sum(1 for term in preferred_terms if _term_matches(label, term))
    score += 20 if operation.interface.startswith("sdk") else 0
    score += 12 if operation.interface == "rest" else 0
    score += 10 if operation.interface == "cli" else 0
    score += 4 * sum(1 for term in preferred_terms if _term_matches(blob, term))
    score += min(len(operation.context), 160) // 40
    return score


def _format_operation(operation: DocumentedOperation) -> str:
    return f"{operation.label} ({operation.interface})"


def _operation_blob(operation: DocumentedOperation) -> str:
    return f"{operation.label} {operation.context} {operation.surface_area}".lower()


def _normalize_candidate(value: str) -> str:
    value = value.strip().strip("$").strip()
    value = re.sub(r"\s+", " ", value)
    if len(value) < 3 or value.lower() in {"true", "false", "none", "null"}:
        return ""
    return value


def _clean_operation(value: str) -> str:
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    return value[:180].strip(" ,.;")


def _clean(value: str) -> str:
    value = re.sub(r"[*_`#>\[\](){}]", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .:-")


def _is_http_operation(value: str) -> bool:
    return bool(_HTTP_RE.search(value))


def _looks_like_sdk_call(value: str) -> bool:
    return bool(_SDK_CALL_RE.search(value)) and "." in value


def _sdk_interface(value: str, context: str) -> str:
    lower = f"{value} {context}".lower()
    if any(term in lower for term in ("await ", "const ", "let ", "=>", "javascript", "typescript", "puppeteer", "connectovercdp")):
        return "sdk:javascript"
    if any(term in lower for term in ("python", "snake_case", "connect_over_cdp", "session_context", "profile_id")):
        return "sdk:python"
    return "sdk:javascript" if any(ch in value for ch in ("{", "}")) else "sdk:python"


def _looks_like_cli(value: str) -> bool:
    if len(value) > 140 or "\n" in value:
        return False
    if value.startswith(("http://", "https://", "/")):
        return False
    if _looks_like_sdk_call(value):
        return False
    return bool(_CLI_RE.match(value))


def _looks_like_prose_operation(value: str) -> bool:
    if len(value) > 220:
        return False
    if not _PROSE_ACTION_RE.search(value):
        return False
    lower = value.lower()
    if lower.startswith(("use this document", "learn how", "this guide", "overview")):
        return False
    return True


def _clean_prose_operation(value: str) -> str:
    value = re.sub(r"^\s{0,4}[-*]\s+", "", value.strip())
    value = re.sub(r"`([^`]+)`", r"\1", value)
    return _clean_operation(_clean(value))


def _action_phrase(value: str, verbs: tuple[str, ...]) -> str:
    cleaned = _clean_prose_operation(value)
    parts = re.split(r"\s*,\s*|\s+and\s+|\s+then\s+", cleaned)
    for part in reversed(parts):
        part = re.sub(r"^(and|then)\s+", "", part.strip(), flags=re.IGNORECASE)
        if any(_term_matches(part, verb) for verb in verbs):
            return part
    return ""


def _prose_interface(value: str, section: str) -> str:
    lower = f"{value} {section}".lower()
    if any(_term_matches(lower, term) for term in ("cli", "command", "terminal")):
        return "cli"
    if any(term in lower for term in ("api", "endpoint", "http", "rest")):
        return "rest"
    if any(term in lower for term in ("sdk", "client.", "python", "javascript", "typescript")):
        return "sdk:python"
    if any(term in lower for term in ("browser", "dashboard", "click", "navigate")):
        return "browser"
    return "docs"


def _term_matches(text: str, term: str) -> bool:
    text = text.lower()
    term = term.lower()
    if "." in term or "_" in term or "/" in term:
        return bool(re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", text))
    return bool(re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", text))


def _is_doc_path(value: str) -> bool:
    lower = value.lower()
    return lower.startswith(
        (
            "/overview/",
            "/cookbook/",
            "/integrations/",
            "/changelog/",
            "/api-reference",
            "/llms",
        )
    )


def _is_api_path(value: str) -> bool:
    lower = value.lower()
    return bool(re.search(r"/v\d+/", lower) or "/api/" in lower or lower.startswith("/api/"))
