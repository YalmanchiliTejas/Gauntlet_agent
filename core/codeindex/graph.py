"""Cross-file dependency graph — the "blast radius" a fix has to account for.

Import edges (file -> file) + call edges (symbol -> called name). Built fresh from the
index each run, never persisted/embedded (CodeRabbit's point: stale indices mislead).
Python is parsed precisely via `ast`; JS/TS/Go get best-effort import edges via regex.

`impacted(graph, names)` answers the question a diff can't: who depends on this code —
the callers and importers a change reaches into beyond the edited lines.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .index import Index, Symbol, _IGNORE, _is_text, build

_JS_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs"}
_IMPORT_JS = re.compile(r"""(?:import\s.*?from\s|require\(\s*)['"]([^'"]+)['"]""")
# ponytail: Python + JS import edges only; add Go when a Go customer repo shows up.


@dataclass
class Graph:
    index: Index
    imports: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))      # file -> files it imports
    imported_by: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))  # file -> files importing it
    callers: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))      # callee name -> caller symbol names
    callees: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))      # caller name -> callee names


def _call_name(func) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _Calls(ast.NodeVisitor):
    """Collect (enclosing_function, called_name) edges, attributed to the nearest def."""
    def __init__(self):
        self.stack: list[str] = []
        self.edges: list[tuple[str, str]] = []

    def visit_FunctionDef(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        callee = _call_name(node.func)
        if callee and self.stack:
            self.edges.append((self.stack[-1], callee))
        self.generic_visit(node)


def _module_to_file(index: Index, module: str) -> str | None:
    """Resolve a dotted python module to a repo-relative file, if it lives in this repo."""
    base = module.replace(".", "/")
    for cand in (f"{base}.py", f"{base}/__init__.py"):
        if cand in index.files:
            return cand
    # fall back to matching the last segment (handles relative/from imports loosely)
    tail = module.split(".")[-1]
    for f in index.files:
        if f.endswith(f"/{tail}.py") or f == f"{tail}.py":
            return f
    return None


def build_graph(index: Index) -> Graph:
    g = Graph(index)
    for rel in index.files:
        p = index.root / rel
        if not _is_text(p):
            continue
        src = p.read_text()
        if rel.endswith(".py"):
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for m in mods:
                    tgt = _module_to_file(index, m)
                    if tgt and tgt != rel:
                        g.imports[rel].add(tgt)
                        g.imported_by[tgt].add(rel)
            v = _Calls()
            v.visit(tree)
            for caller, callee in v.edges:
                g.callers[callee].add(caller)
                g.callees[caller].add(callee)
        elif Path(rel).suffix in _JS_EXT:
            for m in _IMPORT_JS.findall(src):
                tail = m.split("/")[-1].split(".")[0]
                for f in index.files:
                    if Path(f).suffix in _JS_EXT and Path(f).stem == tail and f != rel:
                        g.imports[rel].add(f)
                        g.imported_by[f].add(rel)
    return g


def impacted(graph: Graph, names) -> dict:
    """Blast radius of changing `names` (symbol names): callers, callees, importer files."""
    names = set(names)
    idx = graph.index
    caller_names = set().union(*(graph.callers.get(n, set()) for n in names)) if names else set()
    callee_names = set().union(*(graph.callees.get(n, set()) for n in names)) if names else set()
    files = {s.file for n in names for s in idx.by_name.get(n, [])}
    importer_files = sorted(set().union(*(graph.imported_by.get(f, set()) for f in files)) if files else set())

    def syms(nameset):
        return [s for n in nameset for s in idx.by_name.get(n, [])]

    return {"callers": syms(caller_names - names),
            "callees": syms(callee_names - names),
            "importer_files": importer_files,
            "definition_files": sorted(files)}


def _demo() -> None:
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "lib.py").write_text("def target(x):\n    return x + 1\n")
    (d / "app.py").write_text("from lib import target\n\ndef caller():\n    return target(3)\n")
    g = build_graph(build(d))
    assert "lib.py" in g.imports["app.py"], g.imports
    assert "app.py" in g.imported_by["lib.py"], g.imported_by
    imp = impacted(g, ["target"])
    assert any(s.name == "caller" for s in imp["callers"]), imp
    assert "app.py" in imp["importer_files"], imp
    print("ok")


if __name__ == "__main__":
    _demo()
