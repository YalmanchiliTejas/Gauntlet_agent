"""LLM sender for the judge, vendored so the ported judge has no cross-package dep.

Env-configured, stdlib-only (Gemini or any OpenAI-compatible endpoint). The judge only
calls this when creds are present and no `sender` is injected; with no creds it falls back
to a deterministic rules-only verdict, so this module never needs to succeed for the fix
loop to run. ponytail: mirrors gauntlet.workflows.llm_planner; keep in sync if that changes.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _extract_json_object(text: str) -> dict[str, Any]:
    match = _JSON_BLOCK_RE.search(text)
    if match:
        candidate = match.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("LLM response did not contain a JSON object")
        candidate = text[start : end + 1]
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("LLM JSON root must be an object")
    return data


def _send_prompt(prompt: str) -> str:
    provider = os.environ.get("GAUNTLET_PLANNER_PROVIDER", "").strip().lower()
    if provider == "gemini" or (not provider and os.environ.get("GEMINI_API_KEY")):
        return _send_gemini_prompt(prompt)
    return _send_openai_compatible_prompt(prompt)


def _send_gemini_prompt(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for the Gemini judge")
    model = os.environ.get("GAUNTLET_PLANNER_MODEL", "gemini-2.5-pro")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(url, data=body,
                                headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode())
    return "".join(part.get("text", "")
                   for cand in payload.get("candidates", [])
                   for part in cand.get("content", {}).get("parts", []))


def _send_openai_compatible_prompt(prompt: str) -> str:
    api_key = os.environ.get("GAUNTLET_PLANNER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY, GAUNTLET_PLANNER_API_KEY, or OPENAI_API_KEY is required for the LLM judge")
    base_url = os.environ.get("GAUNTLET_PLANNER_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("GAUNTLET_PLANNER_MODEL", "gpt-4.1")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You judge an AI agent's run. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(f"{base_url}/chat/completions", data=body,
                                 headers={"authorization": f"Bearer {api_key}",
                                          "content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode())
    return payload["choices"][0]["message"]["content"]
