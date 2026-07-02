"""Build a lightweight symbol index of a repo — the map a coder agent navigates by.

Stdlib only: Python via `ast`, JS/TS/Go via regex. No embeddings, no vector store —
the job is "name -> where it's defined", which a symbol table answers exactly and fast.
Heavier semantic search can layer on later if name/text lookup proves insufficient.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_IGNORE = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__",
           ".next", "target", "vendor", ".mypy_cache", ".pytest_cache"}
_TEXT_MAX = 1_000_000

# Regex symbol extractors for non-Python languages: (kind, pattern with one capture group).
_REGEX_LANG = {
    (".js", ".jsx", ".ts", ".tsx", ".mjs"): [
        ("function", re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)")),
        ("class", re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)")),
        ("function", re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(")),
    ],
    (".go",): [
        ("function", re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")),
        ("type", re.compile(r"\btype\s+([A-Za-z_]\w*)")),
    ],
}


@dataclass(frozen=True)
class Symbol:
    name: str
    kind: str      # function | class | type
    file: str      # repo-relative
    line: int


@dataclass
class Index:
    root: Path
    files: list[str] = field(default_factory=list)
    symbols: list[Symbol] = field(default_factory=list)
    by_name: dict[str, list[Symbol]] = field(default_factory=lambda: defaultdict(list))


def _is_text(p: Path) -> bool:
    try:
        if p.stat().st_size > _TEXT_MAX:
            return False
        p.read_text()
        return True
    except (UnicodeDecodeError, OSError):
        return False


def _py_symbols(src: str, rel: str) -> list[Symbol]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(Symbol(node.name, "function", rel, node.lineno))
        elif isinstance(node, ast.ClassDef):
            out.append(Symbol(node.name, "class", rel, node.lineno))
    return out


def _regex_symbols(src: str, rel: str, rules) -> list[Symbol]:
    out = []
    for i, line in enumerate(src.splitlines(), 1):
        for kind, pat in rules:
            m = pat.search(line)
            if m:
                out.append(Symbol(m.group(1), kind, rel, i))
    return out


def build(root: Path) -> Index:
    root = Path(root)
    idx = Index(root)
    for p in sorted(root.rglob("*")):
        if any(part in _IGNORE for part in p.parts):
            continue
        if not p.is_file() or not _is_text(p):
            continue
        rel = str(p.relative_to(root))
        idx.files.append(rel)
        src = p.read_text()
        if p.suffix == ".py":
            syms = _py_symbols(src, rel)
        else:
            rules = next((r for exts, r in _REGEX_LANG.items() if p.suffix in exts), None)
            syms = _regex_symbols(src, rel, rules) if rules else []
        for s in syms:
            idx.symbols.append(s)
            idx.by_name[s.name].append(s)
    return idx


def _demo() -> None:
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / "pkg").mkdir()
    (d / "pkg" / "tools.py").write_text("class Client:\n    def search(self, q):\n        return q\n\ndef send_email(to):\n    pass\n")
    (d / "app.js").write_text("export function handleWebhook(req) {}\nconst search = async () => {}\n")
    (d / "node_modules").mkdir()
    (d / "node_modules" / "junk.js").write_text("function nope(){}\n")
    idx = build(d)
    names = {s.name for s in idx.symbols}
    assert {"Client", "search", "send_email", "handleWebhook"} <= names, names
    assert "nope" not in names, "ignored dir leaked"
    assert idx.by_name["search"][0].kind == "function"
    print("ok")


if __name__ == "__main__":
    _demo()
