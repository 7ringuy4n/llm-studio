#!/usr/bin/env python3
"""Short + long prompt contract for EVERY living llm-studio model (API path).

Progress: running test case N/M. Records wall time and first-token header when present.
Requires LLM_STUDIO_API_KEY and VPN base URL. Does not print secrets.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from prompt_builders import approx_token_filler  # noqa: E402

DEFAULT_MODELS = (
    "Qwen/Qwen3.5-0.8B",
    "Qwen/Qwen3.5-2B",
    "Qwen/Qwen3-8B",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "meta-llama/Llama-3.1-8B-Instruct",
)


def fail(message: str) -> None:
    raise SystemExit(f"all-models prompt contract failed: {message}")


def living_models() -> list[str]:
    raw = os.environ.get("LLM_STUDIO_TEST_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    catalog = Path(__file__).resolve().parents[2] / "configs" / "models.json"
    if catalog.is_file():
        data = json.loads(catalog.read_text())
        ids = []
        for model in data.get("models", []):
            mid = model.get("id")
            # Skip non-living / experimental if tagged; otherwise include allowed set
            if not mid:
                continue
            if mid in DEFAULT_MODELS or model.get("status") == "living":
                ids.append(mid)
        # Prefer DEFAULT order, then any extras
        ordered = [m for m in DEFAULT_MODELS if m in ids] or list(DEFAULT_MODELS)
        return ordered
    return list(DEFAULT_MODELS)


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
            {"role": "system", "content": "Reply briefly and accurately. Do not call tools."},
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
            "X-Session-ID": f"all-models-{label}",
            "X-Correlation-ID": f"all-models-{label}",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=900) as response:
            payload = json.load(response)
            headers = {k.lower(): v for k, v in response.headers.items()}
            status = response.status
    except urllib.error.HTTPError as exc:
        fail(f"{label}: HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as exc:
        fail(f"{label}: {exc.reason}")

    wall_ms = int((time.perf_counter() - started) * 1000)
    choice = (payload.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    if status != 200 or not content:
        fail(f"{label}: status={status} empty={not content}")
    usage = payload.get("usage") or {}
    row = {
        "model": model,
        "label": label,
        "chars_in": len(user_content),
        "wall_ms": wall_ms,
        "first_token_ms": headers.get("x-first-token-latency-ms") or headers.get("x-first-token-ms"),
        "last_token_ms": headers.get("x-last-token-latency-ms") or headers.get("x-last-token-ms"),
        "cache_hit_percent": headers.get("x-cache-hit-percent"),
        "completion_tokens": usage.get("completion_tokens"),
        "prompt_tokens": usage.get("prompt_tokens"),
    }
    print(
        f"  ok {label}: wall_ms={wall_ms} first_token_ms={row['first_token_ms']} "
        f"cache%={row['cache_hit_percent']} out_tokens={row['completion_tokens']}",
        flush=True,
    )
    return row


def main() -> None:
    base_url = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://10.8.0.1:18080/v1").rstrip("/")
    api_key = os.environ.get("LLM_STUDIO_API_KEY", "")
    if not api_key:
        fail("set LLM_STUDIO_API_KEY without printing it")

    models = living_models()
    short = "What is 2+2? Answer with one number only."
    long = (
        approx_token_filler(10000)
        + "\n\nIgnore the tool-trace filler above. Reply with exactly one word: READY"
    )

    case_total = len(models) * 2
    case_n = 0
    rows: list[dict] = []
    for model in models:
        case_n += 1
        rows.append(
            chat(
                base_url=base_url,
                api_key=api_key,
                model=model,
                user_content=short,
                max_tokens=32,
                label=f"{model}::short_prompt",
                case_n=case_n,
                case_total=case_total,
            )
        )
        case_n += 1
        rows.append(
            chat(
                base_url=base_url,
                api_key=api_key,
                model=model,
                user_content=long,
                max_tokens=32,
                label=f"{model}::long_prompt",
                case_n=case_n,
                case_total=case_total,
            )
        )

    out = Path(__file__).resolve().parents[1] / "reports" / "all-models-prompt-perf.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": rows}, indent=2) + "\n")
    print(f"wrote {out}", flush=True)
    print(f"all-models prompt contract PASS: {case_total}/{case_total}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
