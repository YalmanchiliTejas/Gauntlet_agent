"""Read-side of the index: the operations a coder agent calls to navigate code.

  find_symbol(idx, name)      -> definitions matching a name (exact, then substring)
  grep(root, pattern)         -> text matches across the repo (uses), with file:line
  span(root, file, line, ctx) -> numbered source around a line, for reading a definition
"""
from __future__ import annotations

import re
from pathlib import Path

from .index import Index, Symbol, _IGNORE, _is_text


def find_symbol(idx: Index, name: str, limit: int = 20) -> list[Symbol]:
    """Exact name matches first, then case-insensitive substring matches."""
    exact = list(idx.by_name.get(name, []))
    low = name.lower()
    subs = [s for s in idx.symbols if s not in exact and low in s.name.lower()]
    return (exact + subs)[:limit]


def grep(root: Path, pattern: str, limit: int = 50) -> list[tuple[str, int, str]]:
    """Regex search over text files. Returns (relpath, line_no, line). Where a symbol is USED."""
    root = Path(root)
    rx = re.compile(pattern)
    hits: list[tuple[str, int, str]] = []
    for p in sorted(root.rglob("*")):
        if any(part in _IGNORE for part in p.parts) or not p.is_file() or not _is_text(p):
            continue
        rel = str(p.relative_to(root))
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if rx.search(line):
                hits.append((rel, i, line.strip()[:200]))
                if len(hits) >= limit:
                    return hits
    return hits


def span(root: Path, rel: str, line: int, ctx: int = 8) -> str:
    """Numbered source lines around `line` — the chunk an agent reads to understand a def."""
    p = Path(root) / rel
    if not p.is_file():
        return f"error: no such file {rel}"
    lines = p.read_text().splitlines()
    lo, hi = max(0, line - 1 - ctx), min(len(lines), line + ctx)
    return "\n".join(f"{i+1:>5}  {lines[i]}" for i in range(lo, hi))


def _demo() -> None:
    import tempfile
    from .index import build
    d = Path(tempfile.mkdtemp())
    (d / "t.py").write_text("def search(q):\n    return q\n\ndef caller():\n    return search('x')\n")
    idx = build(d)
    assert find_symbol(idx, "search")[0].line == 1
    assert any("substring" not in s.name for s in find_symbol(idx, "sea"))  # substring match works
    uses = grep(d, r"\bsearch\(")
    assert any(u[1] == 5 for u in uses), uses          # the call site
    assert "def search" in span(d, "t.py", 1, 2)
    print("ok")


if __name__ == "__main__":
    _demo()
