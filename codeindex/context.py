"""Assemble the cross-file context bundle that grounds the fixer (and inspection agent).

Given the symbols a finding touches, gather their definitions plus the callers/importers a
change reaches into (via the dependency graph), as compact source spans. Optionally compress
to fit a budget — CodeRabbit's "4000-line file becomes the few functions the change touches"
(here, span windows already do most of that; the LLM pass only kicks in over budget).
"""
from __future__ import annotations

import json

from .graph import build_graph, impacted
from .index import build
from .query import span

_BUDGET = 12_000  # chars before we ask a cheap model to compress


def context_for(root, names, ctx: int = 8) -> dict:
    """names: symbol names a finding touches. Returns a grounding bundle (no LLM)."""
    idx = build(root)
    g = build_graph(idx)
    imp = impacted(g, names)

    def spans(symbols, limit=12):
        out = []
        for s in symbols[:limit]:
            out.append({"symbol": s.name, "file": s.file, "line": s.line,
                        "source": span(root, s.file, s.line, ctx)})
        return out

    targets = [s for n in names for s in idx.by_name.get(n, [])]
    return {
        "targets": list(dict.fromkeys(names)),
        "definitions": spans(targets),
        "callers": spans(imp["callers"]),          # who depends on the changed code
        "importer_files": imp["importer_files"],
    }


def render(bundle: dict) -> str:
    parts = [f"Targets: {', '.join(bundle['targets'])}"]
    for label in ("definitions", "callers"):
        for item in bundle.get(label, []):
            parts.append(f"\n# {label[:-1]}: {item['symbol']} ({item['file']}:{item['line']})\n{item['source']}")
    if bundle.get("importer_files"):
        parts.append("\nImporter files (dependents): " + ", ".join(bundle["importer_files"]))
    return "\n".join(parts)


def compress(text: str, sender=None, budget: int = _BUDGET) -> str:
    """Summarize to fit the budget only when over it; otherwise pass through unchanged."""
    if len(text) <= budget or sender is None:
        return text[:budget] if sender is None else text
    prompt = ("Compress this code context for a fixer agent: keep signatures, control flow, and "
              "anything a caller depends on; drop boilerplate. Stay well under "
              f"{budget} chars.\n\n{text}")
    try:
        return sender(prompt)
    except Exception:
        return text[:budget]  # never fail context-building on an LLM blip


def _demo() -> None:
    import tempfile
    from pathlib import Path
    d = Path(tempfile.mkdtemp())
    (d / "lib.py").write_text("def target(x):\n    return x + 1\n")
    (d / "app.py").write_text("from lib import target\n\ndef caller():\n    return target(3)\n")
    b = context_for(d, ["target"])
    assert b["definitions"][0]["symbol"] == "target"
    assert any(c["symbol"] == "caller" for c in b["callers"]), b
    assert "app.py" in b["importer_files"]
    txt = render(b)
    assert "def target" in txt and "def caller" in txt
    assert compress("x" * 100, budget=50) == "x" * 50          # no sender -> truncate
    assert compress("short", sender=lambda p: "SUMMARY") == "short"  # under budget -> passthrough
    assert compress("y" * 100, sender=lambda p: "SUMMARY", budget=50) == "SUMMARY"
    print("ok")


if __name__ == "__main__":
    _demo()
