"""The verification loop — never trust a single-shot patch.

Each iteration: coder edits the work copy → `verify(root)` re-runs scans + tests + simulations
+ judge → if all clean, stop; else feed the concrete failures back and iterate, to a budget.
Source-agnostic: `coder` and `verify` are injected so the loop is unit-testable without AWS/LLM.
"""
from __future__ import annotations

import difflib
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


async def _maybe_await(v):
    """Let coder/verify be sync (tests) or async (real microVM run)."""
    return await v if inspect.isawaitable(v) else v

from .base import Coder, Finding

_TEXT_MAX = 1_000_000


def _is_text(p: Path) -> bool:
    try:
        if p.stat().st_size > _TEXT_MAX:
            return False
        p.read_text()
        return True
    except (UnicodeDecodeError, OSError):
        return False


def snapshot(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): p.read_text()
            for p in root.rglob("*") if p.is_file() and _is_text(p)}


def unified_diff(before: dict[str, str], root: Path) -> str:
    out = []
    after = snapshot(root)
    for rel in sorted(set(before) | set(after)):
        old, new = before.get(rel, ""), after.get(rel, "")
        if old != new:
            out += difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        f"a/{rel}", f"b/{rel}")
    return "".join(out)


# verify(root) -> (all_clean: bool, failures_text: str, remaining: list[Finding])
Verify = Callable[[Path], tuple[bool, str, list[Finding]]]


@dataclass
class FixResult:
    converged: bool
    iterations: int
    diff: str
    remaining: list[Finding] = field(default_factory=list)
    history: list[bool] = field(default_factory=list)


async def fix_loop(root: Path, findings: list[Finding], coder: Coder, verify: Verify,
                   context_fn: Callable[[Path, list[Finding]], str] | None = None,
                   max_iters: int = 4) -> FixResult:
    root = Path(root)
    before = snapshot(root)
    failures = ""
    remaining = findings
    history: list[bool] = []
    converged = False
    i = 0
    for i in range(max_iters):
        ctx = context_fn(root, remaining) if context_fn else ""
        # Give the (stateless) coder memory of its own prior edits so it doesn't re-propose
        # a change that already failed to converge.
        attempted = unified_diff(before, root)
        fb = failures
        if attempted:
            fb += ("\n\n## Changes already attempted (did NOT resolve the above — try a different fix)\n"
                   f"```diff\n{attempted[:4000]}\n```")
        await _maybe_await(coder.propose(root, remaining, ctx, fb))
        converged, failures, remaining = await _maybe_await(verify(root))
        history.append(converged)
        if converged:
            break
    return FixResult(converged, i + 1, unified_diff(before, root), remaining, history)


def _demo() -> None:
    import asyncio
    import tempfile
    d = Path(tempfile.mkdtemp())
    findings = [Finding("reliability", "x must reach 3")]

    class Bump:  # a stub coder: +1 each call (mimics an agent making progress)
        def __init__(self):
            self.seen: list[str] = []  # records the `failures` arg each call

        def propose(self, root, fnds, context, failures=""):
            self.seen.append(failures)
            cur = int((root / "a.py").read_text().split("=")[1])
            (root / "a.py").write_text(f"x = {cur + 1}\n")
            return "bumped"

    def verify(root):  # sync stub — the loop also accepts an async verify
        ok = int((root / "a.py").read_text().split("=")[1]) >= 3
        return ok, ("" if ok else "x still < 3"), ([] if ok else findings)

    async def run():
        (d / "a.py").write_text("x = 1\n")
        bump = Bump()
        r = await fix_loop(d, findings, bump, verify, max_iters=4)
        assert r.converged and r.iterations == 2, r        # 1->2->3 across two iters
        assert "+x = 3" in r.diff and "-x = 1" in r.diff, r.diff
        assert r.remaining == []
        # fix #2: the coder is amnesiac, so the loop feeds back its own prior edits.
        assert bump.seen[0] == "", bump.seen                       # nothing attempted yet
        assert "already attempted" in bump.seen[1], bump.seen      # iter 2 sees iter-1 diff
        assert "+x = 2" in bump.seen[1], bump.seen
        (d / "a.py").write_text("x = 1\n")
        r2 = await fix_loop(d, findings, Bump(), verify, max_iters=1)
        assert not r2.converged and r2.remaining == findings, r2  # honest, not false success

    asyncio.run(run())
    print("ok")


if __name__ == "__main__":
    _demo()
