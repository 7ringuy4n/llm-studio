#!/usr/bin/env python3
"""Live API contract test for DSH-style web-search tool calling."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def fail(message: str) -> None:
    raise SystemExit(f"web-search contract failed: {message}")


def main() -> None:
    base_url = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://127.0.0.1:18080/v1").rstrip("/")
    api_key = os.environ.get("LLM_STUDIO_API_KEY", "")
    model = os.environ.get("LLM_STUDIO_TEST_MODEL", "Qwen/Qwen3.5-0.8B")
    if not api_key:
        fail("set LLM_STUDIO_API_KEY without printing it")

    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "For current information, call the provided web_search tool.",
            },
            {
                "role": "user",
                "content": "Search for the official OpenObserve GitHub repository.",
            },
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the public web for current information.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ],
        "tool_choice": "required",
        "parallel_tool_calls": False,
        "temperature": 0,
        "max_tokens": 128,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Session-ID": "web-search-contract-test",
            "X-Correlation-ID": "web-search-contract-test",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        fail(f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as exc:
        fail(str(exc.reason))

    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    calls = message.get("tool_calls") or []
    if choice.get("finish_reason") != "tool_calls":
        fail(f"finish_reason was {choice.get('finish_reason')!r}")
    if len(calls) != 1:
        fail(f"expected one tool call, received {len(calls)}")
    function = calls[0].get("function") or {}
    if function.get("name") != "web_search":
        fail(f"expected web_search, received {function.get('name')!r}")
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except json.JSONDecodeError as exc:
        fail(f"tool arguments are not JSON: {exc}")
    if not isinstance(arguments.get("query"), str) or not arguments["query"].strip():
        fail("web_search query is empty")

    usage = payload.get("usage") or {}
    print(
        "web-search contract passed: "
        f"model={payload.get('model')} tool=web_search total_tokens={usage.get('total_tokens')}"
    )


if __name__ == "__main__":
    main()
