"""The fixer: turn findings (security / redundancy / reliability / simulation) into verified
code changes. `base` defines the common Finding + Coder protocol; `loop` runs the
apply→verify cycle; `codex` is the default coder; `output` opens the PR.
"""
