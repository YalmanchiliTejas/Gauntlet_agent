"""Codebase index: name -> code location -> source span, for two consumers.

  index.build(root)            -> a symbol/file index (Python via ast, JS/TS/Go via regex)
  query.find_symbol/grep/span  -> the navigation a coder agent uses
  probe.from_trajectory/from_issue -> judge finding / trace -> affected code
  probe.repo_context           -> structured repo summary for workflow generation

Stdlib only, no embeddings — symbol lookup answers "where is this defined" exactly.
A semantic/embedding layer can sit alongside later if name+text lookup falls short.
"""

from .index import build  # noqa: F401
