"""Small JSON-RPC probe for optional MCP tool discovery."""

from __future__ import annotations

import json
import urllib.request
from typing import Any


def fetch_mcp_tools(server_url: str, timeout_seconds: float = 2.0) -> list[dict[str, Any]]:
    """Fetch `tools/list` from an HTTP JSON-RPC MCP server.

    Network discovery is best-effort for MVP generation. Callers should treat an
    empty list as "no tools discovered" and keep generation deterministic.
    """
    body = json.dumps({"jsonrpc": "2.0", "id": "gauntlet-tools-list", "method": "tools/list", "params": {}}).encode()
    request = urllib.request.Request(
        server_url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode())
    except Exception:
        return []
    result = payload.get("result") if isinstance(payload, dict) else None
    tools = result.get("tools") if isinstance(result, dict) else None
    if isinstance(tools, list):
        return [tool for tool in tools if isinstance(tool, dict)]
    return []
