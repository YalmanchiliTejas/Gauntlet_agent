"""Format the fixer's result for humans — the PR body (converged) or an honest report (not).

Pure formatting; the actual branch/commit/PR call lives in the job orchestration using the
github helpers + `FixResult.diff`. Kept separate so it's unit-testable.
"""
from __future__ import annotations

from findings import Finding, summary
from .loop import FixResult


def pr_body(result: FixResult, fixed: list[Finding],
            before_verdict: str, after_verdict: str) -> str:
    return "\n".join([
        "Automated fix from Gauntlet — verified against tests + simulations + judge.",
        "",
        f"**Simulation verdict:** `{before_verdict}` → `{after_verdict}`",
        f"**Iterations:** {result.iterations}",
        "",
        "## Issues fixed",
        summary(fixed),
        "",
        "Each change was applied and re-verified in a loop; the PR is opened only because all "
        "axes (security/reliability scans, tests, simulations, judge) came back clean.",
    ])


def report(result: FixResult, before_verdict: str) -> str:
    """When the loop can't fully verify — no PR; say so honestly with what's left."""
    lines = [f"Gauntlet fix loop did not converge in {result.iterations} iteration(s); no PR opened.",
             f"Starting simulation verdict: `{before_verdict}`.", ""]
    if result.remaining:
        lines += ["Remaining findings:", summary(result.remaining)]
    if result.diff:
        lines += ["", "Best-effort diff (not applied):", "```diff", result.diff[:40_000], "```"]
    return "\n".join(lines)


def _demo() -> None:
    fixed = [Finding("security", "hardcoded key", "high", file="cfg.py", line=2)]
    r = FixResult(converged=True, iterations=2, diff="--- a/cfg.py\n+++ b/cfg.py\n", remaining=[])
    body = pr_body(r, fixed, "fail", "pass")
    assert "`fail` → `pass`" in body and "### security" in body, body
    r2 = FixResult(converged=False, iterations=4, diff="", remaining=fixed)
    rep = report(r2, "fail")
    assert "did not converge" in rep and "Remaining findings" in rep, rep
    print("ok")


if __name__ == "__main__":
    _demo()
