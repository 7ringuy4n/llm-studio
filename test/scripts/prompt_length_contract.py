#!/usr/bin/env python3
"""Live chat contract: short prompt and long prompt against a running API."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def fail(message: str) -> None:
    raise SystemExit(f"prompt-length contract failed: {message}")


def chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    user_content: str,
    max_tokens: int,
    label: str,
    case_n: int,
    case_total: int,
) -> dict:
    print(f"running test case {case_n}/{case_total}: {label}", flush=True)
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Reply briefly and accurately."},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Session-ID": f"prompt-length-{label}",
            "X-Correlation-ID": f"prompt-length-{label}",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            payload = json.load(response)
            status = response.status
            headers = {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as exc:
        fail(f"{label}: HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as exc:
        fail(f"{label}: {exc.reason}")

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = (message.get("content") or "").strip()
    if status != 200:
        fail(f"{label}: status {status}")
    if not content:
        fail(f"{label}: empty content")
    usage = payload.get("usage") or {}
    print(
        f"  ok {label}: chars_in={len(user_content)} "
        f"completion_tokens={usage.get('completion_tokens')} "
        f"wall_ms={elapsed_ms} "
        f"first_token_ms={headers.get('x-first-token-latency-ms', 'n/a')}",
        flush=True,
    )
    return payload


def main() -> None:
    base_url = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://10.8.0.1:18080/v1").rstrip("/")
    api_key = os.environ.get("LLM_STUDIO_API_KEY", "")
    model = os.environ.get("LLM_STUDIO_TEST_MODEL", "Qwen/Qwen3.5-0.8B")
    if not api_key:
        fail("set LLM_STUDIO_API_KEY without printing it")

    short = "What is 2+2? Answer with one number only."
    # ~2–3k tokens of filler + a verifiable ask (long prompt / context pressure)
    filler = ("Context note: keep the final answer as a single uppercase word. " * 120)
    long = (
        filler
        + "\n\nIgnore the filler above. Reply with exactly one word: READY"
    )

    case_total = 2
    chat(
        base_url=base_url,
        api_key=api_key,
        model=model,
        user_content=short,
        max_tokens=32,
        label="short_prompt",
        case_n=1,
        case_total=case_total,
    )
    chat(
        base_url=base_url,
        api_key=api_key,
        model=model,
        user_content=long,
        max_tokens=32,
        label="long_prompt",
        case_n=2,
        case_total=case_total,
    )
    print("prompt-length contract PASS: 2/2", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
