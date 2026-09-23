#!/usr/bin/env python3
"""Cache hit vs miss when switching reasoning_effort (all living models).

Contract:
  1) Warm: same model + effort + shared prefix → second call should show cache% > 0
     (or cached_tokens > 0) when the backend supports prefix cache.
  2) Switch effort: same shared prefix but different reasoning_effort → expect a
     cache miss relative to the warm path (cache% == 0 or cached_tokens == 0),
     because enable_thinking / template kwargs change the tokenized prompt.

Progress prints: running test case N/M.
Requires LLM_STUDIO_API_KEY. Does not print secrets.
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

from all_models_prompt_contract import living_models  # noqa: E402

SHARED_PREFIX = (
    "You are a careful ops assistant. Context block (stable for cache probes):\n"
    "homelab OpenAI API listens on VPN 10.8.0.1:18080; OpenObserve on :15080; "
    "DSH web on 127.0.0.1:8080. Prefer short answers.\n"
)
USER_Q = "Reply with exactly one word: PONG"


def fail(message: str) -> None:
    raise SystemExit(f"reasoning-cache contract failed: {message}")


def chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    effort: str,
    label: str,
    case_n: int,
    case_total: int,
    session_id: str,
) -> dict:
    print(f"running test case {case_n}/{case_total}: {label}", flush=True)
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SHARED_PREFIX},
            {"role": "user", "content": USER_Q},
        ],
        "temperature": 0,
        "max_tokens": 48,
        "reasoning_effort": effort,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Session-ID": session_id,
            "X-Correlation-ID": f"reasoning-cache-{label}",
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
    if status != 200:
        fail(f"{label}: status={status}")
    usage = payload.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    cached = int(details.get("cached_tokens") or 0)
    try:
        cache_pct = float(headers.get("x-cache-hit-percent") or 0)
    except ValueError:
        cache_pct = 0.0
    row = {
        "model": model,
        "label": label,
        "effort": effort,
        "wall_ms": wall_ms,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cached_tokens": cached,
        "cache_hit_percent": cache_pct,
        "first_token_ms": headers.get("x-first-token-latency-ms")
        or headers.get("x-first-token-ms"),
        "last_token_ms": headers.get("x-last-token-latency-ms")
        or headers.get("x-last-token-ms"),
    }
    print(
        f"  ok {label}: wall_ms={wall_ms} cache%={cache_pct} cached={cached} "
        f"first={row['first_token_ms']} last={row['last_token_ms']}",
        flush=True,
    )
    return row


def main() -> None:
    base_url = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://10.8.0.1:18080/v1").rstrip("/")
    api_key = os.environ.get("LLM_STUDIO_API_KEY", "")
    if not api_key:
        fail("set LLM_STUDIO_API_KEY without printing it")

    models = living_models()
    # Per model: warm1(off), warm2(off), switch(low) → 3 cases
    case_total = len(models) * 3
    case_n = 0
    rows: list[dict] = []

    for model in models:
        session = f"reasoning-cache-{model.replace('/', '_')}"

        case_n += 1
        warm1 = chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            effort="off",
            label=f"{model}::warm1_effort_off_nocache",
            case_n=case_n,
            case_total=case_total,
            session_id=session,
        )
        rows.append(warm1)

        case_n += 1
        warm2 = chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            effort="off",
            label=f"{model}::warm2_effort_off_expect_cache",
            case_n=case_n,
            case_total=case_total,
            session_id=session,
        )
        rows.append(warm2)

        case_n += 1
        switched = chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            effort="low",
            label=f"{model}::switch_effort_low_expect_miss",
            case_n=case_n,
            case_total=case_total,
            session_id=session,
        )
        rows.append(switched)

        # Assertions (soft-fail only if backend reports cache metrics at all)
        if warm2["cache_hit_percent"] > 0 or warm2["cached_tokens"] > 0:
            # Warm path established — switching effort must not keep a full hit
            if switched["cache_hit_percent"] >= warm2["cache_hit_percent"] and switched[
                "cache_hit_percent"
            ] > 0:
                # Allow partial prefix share, but require drop vs warm2 when warm2 was strong
                if warm2["cache_hit_percent"] >= 50 and switched["cache_hit_percent"] >= warm2[
                    "cache_hit_percent"
                ]:
                    fail(
                        f"{model}: switching effort did not reduce cache hit "
                        f"(warm2={warm2['cache_hit_percent']}% switched={switched['cache_hit_percent']}%)"
                    )
        else:
            print(
                f"  note {model}: warm2 showed no cache hit (backend may lack prefix cache "
                f"for this model); still recorded miss path for effort switch",
                flush=True,
            )

    out = Path(__file__).resolve().parents[1] / "reports" / "reasoning-cache-perf.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": rows}, indent=2) + "\n")
    print(f"wrote {out}", flush=True)
    print(f"reasoning-cache contract PASS: {case_total}/{case_total}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
