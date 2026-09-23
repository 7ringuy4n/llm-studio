#!/usr/bin/env python3
"""Real-world API lab: short/long, continuous multi-turn, and concurrent requests.

Covers every living model by default. Progress: running test case N/M.
Requires LLM_STUDIO_API_KEY. Does not print secrets.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow importing sibling prompt_builders when run as a script.
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from prompt_builders import SHORT_REAL, LONG_REAL_QUESTION, long_realworld_prompt  # noqa: E402

DEFAULT_MODELS = (
    "Qwen/Qwen3.5-0.8B",
    "Qwen/Qwen3.5-2B",
    "Qwen/Qwen3-8B",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "meta-llama/Llama-3.1-8B-Instruct",
)

LONG_REAL = long_realworld_prompt(LONG_REAL_QUESTION, target_tokens=10000)


def fail(message: str) -> None:
    raise SystemExit(f"realworld-api contract failed: {message}")


def living_models() -> list[str]:
    raw = os.environ.get("LLM_STUDIO_TEST_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    return list(DEFAULT_MODELS)


def post_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    session_id: str,
    max_tokens: int = 96,
) -> tuple[dict, dict[str, str], int]:
    body = {
        "model": model,
        "messages": messages,
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
            "X-Session-ID": session_id,
            "X-Correlation-ID": session_id,
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
        fail(f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as exc:
        fail(str(exc.reason))
    wall_ms = int((time.perf_counter() - started) * 1000)
    if status != 200:
        fail(f"status {status}")
    content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if not content.strip():
        fail("empty content")
    return payload, headers, wall_ms


def main() -> None:
    base_url = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://10.8.0.1:18080/v1").rstrip("/")
    api_key = os.environ.get("LLM_STUDIO_API_KEY", "")
    if not api_key:
        fail("set LLM_STUDIO_API_KEY without printing it")

    models = living_models()
    # Per model: short, long, continuous(3 turns counted as 1 case block but 3 posts), concurrent
    # Case accounting: each model → 4 named cases (short, long, continuous, concurrent)
    case_total = len(models) * 4
    case_n = 0
    rows: list[dict] = []

    for model in models:
        session = f"realworld-{model.replace('/', '_')}"

        case_n += 1
        print(f"running test case {case_n}/{case_total}: {model}::short_realworld", flush=True)
        _, headers, wall = post_chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": "You are a concise homelab ops assistant."},
                {"role": "user", "content": SHORT_REAL},
            ],
            session_id=f"{session}-short",
            max_tokens=64,
        )
        rows.append(
            {
                "model": model,
                "kind": "short_realworld",
                "wall_ms": wall,
                "first_token_ms": headers.get("x-first-token-ms") or headers.get("x-first-token-latency-ms"),
                "cache_hit_percent": headers.get("x-cache-hit-percent"),
            }
        )
        print(f"  ok short wall_ms={wall} first={rows[-1]['first_token_ms']}", flush=True)

        case_n += 1
        print(f"running test case {case_n}/{case_total}: {model}::long_realworld", flush=True)
        _, headers, wall = post_chat(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=[
                {"role": "system", "content": "You are a concise homelab ops assistant."},
                {"role": "user", "content": LONG_REAL},
            ],
            session_id=f"{session}-long",
            max_tokens=128,
        )
        rows.append(
            {
                "model": model,
                "kind": "long_realworld",
                "wall_ms": wall,
                "first_token_ms": headers.get("x-first-token-ms") or headers.get("x-first-token-latency-ms"),
                "cache_hit_percent": headers.get("x-cache-hit-percent"),
            }
        )
        print(f"  ok long wall_ms={wall} first={rows[-1]['first_token_ms']}", flush=True)

        case_n += 1
        print(f"running test case {case_n}/{case_total}: {model}::continuous_messages", flush=True)
        continuous_session = f"{session}-continuous"
        turns = [
            "We run llm-studio behind Traefik on VPN. What port should DSH use for the API?",
            "Thanks. If OpenObserve is on 15080, what should I leave free on a 4-vCPU host?",
            "Summarize those two answers in one sentence.",
        ]
        history: list[dict] = [
            {"role": "system", "content": "You are a concise homelab ops assistant."}
        ]
        cont_walls: list[int] = []
        for turn in turns:
            history.append({"role": "user", "content": turn})
            payload, headers, wall = post_chat(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=history,
                session_id=continuous_session,
                max_tokens=80,
            )
            reply = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            history.append({"role": "assistant", "content": reply})
            cont_walls.append(wall)
        rows.append(
            {
                "model": model,
                "kind": "continuous_messages",
                "turns": len(turns),
                "wall_ms_per_turn": cont_walls,
                "wall_ms_total": sum(cont_walls),
            }
        )
        print(f"  ok continuous turns={len(turns)} walls={cont_walls}", flush=True)

        case_n += 1
        print(f"running test case {case_n}/{case_total}: {model}::concurrency", flush=True)
        # API max_concurrent_requests is typically 1 — expect queueing, not corruption.
        def one(i: int) -> int:
            _, _, wall_ms = post_chat(
                base_url=base_url,
                api_key=api_key,
                model=model,
                messages=[
                    {"role": "user", "content": f"Concurrent probe {i}: reply with the digit {i} only."}
                ],
                session_id=f"{session}-conc-{i}",
                max_tokens=16,
            )
            return wall_ms

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(one, i) for i in range(3)]
            conc_walls = [f.result() for f in as_completed(futures)]
        rows.append(
            {
                "model": model,
                "kind": "concurrency",
                "workers": 3,
                "wall_ms": conc_walls,
                "wall_ms_max": max(conc_walls),
            }
        )
        print(f"  ok concurrency walls={conc_walls}", flush=True)

    out = Path(__file__).resolve().parents[1] / "reports" / "realworld-api-perf.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": rows}, indent=2) + "\n")
    print(f"wrote {out}", flush=True)
    print(f"realworld-api contract PASS: {case_total}/{case_total}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
