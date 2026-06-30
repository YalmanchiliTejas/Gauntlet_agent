"""Shim: expose the find-and-fix job (fixer.job) under gauntlet.* for the webhook handler."""
from fixer.job import submit  # noqa: F401
