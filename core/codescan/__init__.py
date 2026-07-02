"""Code inspection: security + code-level reliability findings.

(Named `codescan` not `inspect` to avoid shadowing the stdlib `inspect` module.)
`static` runs scanners (semgrep/bandit/...) and parses them to the common Finding shape;
`investigate` is the generated-CLI agent that finds what linters miss. Both take an injectable
command runner so they work locally now and against the microVM `/exec` sandbox later.
"""
