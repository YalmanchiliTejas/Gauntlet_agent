"""Redact secrets before any trajectory text reaches the judge LLM.

Tool args routinely carry tokens / PII; shipping them to an external model is the
exact leak the judge is supposed to catch. Mask by key name and by obvious token
shapes. Lossy on purpose — the judge needs the shape of a call, not its credentials.
"""
from __future__ import annotations

import re

_SENSITIVE_KEY = re.compile(r"token|secret|password|passwd|api[_-]?key|authorization|auth|credential|cookie|session", re.I)
_MASK = "***REDACTED***"

# Bearer headers, sk-/ghp_-style keys, JWTs, and long opaque hex/base64 blobs.
_PATTERNS = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"\b(?:sk|pk|ghp|gho|xox[baprs])[-_][A-Za-z0-9]{8,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9._\-]{20,}\b"),                 # JWT
    re.compile(r"\b[A-Fa-f0-9]{32,}\b"),                        # long hex
]


def redact_str(s: str) -> str:
    for p in _PATTERNS:
        s = p.sub(_MASK, s)
    return s


def redact(obj):
    """Recursively mask sensitive values in dicts/lists/strings; other types pass through."""
    if isinstance(obj, dict):
        return {k: (_MASK if isinstance(k, str) and _SENSITIVE_KEY.search(k) else redact(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str):
        return redact_str(obj)
    return obj


def _demo() -> None:
    out = redact({"args": {"api_key": "abc", "to": "x", "note": "Bearer sk-livefoobar12345678"}})
    assert out["args"]["api_key"] == _MASK, out
    assert out["args"]["to"] == "x", out
    assert _MASK in out["args"]["note"], out
    assert redact_str("auth eyJabcdefghijklmnopqrstuvwxyz0123") .count(_MASK) == 1
    print("ok")


if __name__ == "__main__":
    _demo()
