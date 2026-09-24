#!/usr/bin/env python3
"""Continuous multi-turn growth to near-max context (coding-agent style).

Simulates a DSH/coding-agent session: each turn appends code + tool-trace filler
and asks for a short ACK, growing the conversation until:

  * provider rejects (context exceeded / HTTP 4xx/5xx), or
  * cumulative prompt tokens reach ~catalog context_tokens (or CAP), or
  * MAX_TURNS hit.

Records whether the session can **continue** near the limit vs hard-fail.
DSH UI auto-compact is covered separately by `dsh_web_compact_flood.sh`
(Standard mode); this lab is the OpenAI-API / Ollama continuous SoT.

Env:
  VAST_TEST_BASE_URL or LLM_STUDIO_TEST_BASE_URL (required)
  VAST_API_KEY / LLM_STUDIO_API_KEY (optional for local Ollama)
  LLM_STUDIO_TEST_MODELS / VAST_CYCLE_MODELS (optional filter)
  CODING_CTX_MAX_TURNS (default 40)
  CODING_CTX_CHUNK_TOKENS (default scales from that model's test ctx) — filler/turn
  CODING_CTX_CAP (optional hard prompt-token cap; default that model's test ctx - 512)
  CODING_CTX_CONTINUE_AFTER_OK (default 3) — extra turns after hitting ≥90% ctx

Per-model rule: each catalog entry uses its own ollama_num_ctx /
test_context_tokens / context_tokens. No shared global ctx clamp (no common 4k/32k).

Progress: running test case N/M
Artifact: docs/perf-results/coding-agent-max-ctx-compact.jsonl
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
ROOT = _SCRIPTS.parents[1]  # llm-studio/ (scripts → test → studio; parents[1]=studio)
sys.path.insert(0, str(_SCRIPTS))

from prompt_builders import approx_token_filler  # noqa: E402
from model_ctx import (  # noqa: E402
    OLLAMA_MAP,
    ollama_tag,
    test_context_tokens,
)

CATALOG = ROOT / "configs" / "models.json"
OUT = ROOT / "docs" / "perf-results" / "coding-agent-max-ctx-compact.jsonl"


def fail(msg: str) -> None:
    raise SystemExit(f"coding-agent max-ctx lab failed: {msg}")


def request_json(url: str, key: str, body: dict, timeout: int = 1800):
    hdrs = {"Content-Type": "application/json"}
    if key:
        hdrs["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=hdrs, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.load(resp), {k.lower(): v for k, v in resp.headers.items()}


def coding_turn_content(turn: int, chunk_tokens: int) -> str:
    """Coding-agent style user turn: patch request + growing tool-trace body."""
    filler = approx_token_filler(chunk_tokens)
    return (
        f"[coding-agent turn={turn}] Continue the session.\n"
        f"Task: edit `src/util.py` — add `def add(a, b): return a + b`.\n"
        f"Prior tool traces / file dumps (noise, keep attending to ACK):\n"
        f"{filler}\n\n"
        f"Reply with exactly: ACK{turn} and one line: return a + b"
    )


def run_model(
    *,
    base: str,
    key: str,
    catalog_id: str,
    run_name: str,
    context_tokens: int,
    n_start: int,
    total: int,
) -> tuple[list[dict], int]:
    max_turns = int(os.environ.get("CODING_CTX_MAX_TURNS", "40"))
    # Scale filler with this model's window when unset (not a shared default suite)
    default_chunk = max(256, min(4096, context_tokens // 32))
    chunk = int(os.environ.get("CODING_CTX_CHUNK_TOKENS", str(default_chunk)))
    cap_env = os.environ.get("CODING_CTX_CAP", "").strip()
    cap = int(cap_env) if cap_env else max(1024, context_tokens - 512)
    continue_after = int(os.environ.get("CODING_CTX_CONTINUE_AFTER_OK", "3"))

    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                "You are a coding agent in a long session. Prefer short replies. "
                "When asked for ACKN, reply exactly that token plus the one-line code."
            ),
        }
    ]
    rows: list[dict] = []
    n = n_start
    hit_near_max = False
    continue_budget = 0
    outcome = "max_turns"

    for turn in range(1, max_turns + 1):
        n += 1
        label = f"{catalog_id}/coding-max-ctx/turn-{turn}"
        print(f"running test case {n}/{total}: {label}", flush=True)
        messages.append({"role": "user", "content": coding_turn_content(turn, chunk)})
        body = {
            "model": run_name,
            "messages": messages,
            "max_tokens": 48,
            "temperature": 0,
            "stream": False,
        }
        t0 = time.perf_counter()
        try:
            status, payload, headers = request_json(
                f"{base}/chat/completions", key, body, timeout=1800
            )
            usage = payload.get("usage") or {}
            msg = (payload.get("choices") or [{}])[0].get("message") or {}
            content = msg.get("content") or ""
            details = usage.get("prompt_tokens_details") or {}
            cached = details.get("cached_tokens")
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            cache_pct = (
                round(cached / prompt_tokens * 100, 2)
                if prompt_tokens and cached is not None
                else None
            )
            row = {
                "label": label,
                "model": run_name,
                "catalog_id": catalog_id,
                "ok": status == 200,
                "http_status": status,
                "turn": turn,
                "wall_s": round(time.perf_counter() - t0, 3),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": usage.get("completion_tokens"),
                "cached_tokens": cached,
                "cache_hit_percent": cache_pct,
                "context_tokens_catalog": context_tokens,
                "context_cap": cap,
                "pct_of_cap": round(prompt_tokens / cap * 100, 1) if cap else None,
                "content_preview": content[:160],
                "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason"),
                "continued_after_near_max": hit_near_max,
            }
            # Keep assistant turn so next request is true multi-turn growth
            messages.append({"role": "assistant", "content": content or f"ACK{turn}"})
            rows.append(row)

            if prompt_tokens >= int(0.9 * cap):
                if not hit_near_max:
                    hit_near_max = True
                    continue_budget = continue_after
                    outcome = "near_max_continue"
                else:
                    continue_budget -= 1
                    if continue_budget <= 0:
                        outcome = "continued_ok_near_max"
                        break
            if prompt_tokens >= cap:
                outcome = "hit_cap_continue_ok"
                break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:800]
            overflow = any(
                s in detail.lower()
                for s in (
                    "context",
                    "n_ctx",
                    "num_ctx",
                    "too long",
                    "maximum",
                    "overflow",
                    "exceed",
                )
            )
            rows.append(
                {
                    "label": label,
                    "model": run_name,
                    "catalog_id": catalog_id,
                    "ok": False,
                    "http_status": exc.code,
                    "turn": turn,
                    "wall_s": round(time.perf_counter() - t0, 3),
                    "error": detail,
                    "context_overflow_like": overflow,
                    "outcome_hint": "overflow_or_reject",
                    "continued_after_near_max": hit_near_max,
                }
            )
            outcome = "overflow_or_reject" if overflow else "http_error"
            break
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "label": label,
                    "model": run_name,
                    "catalog_id": catalog_id,
                    "ok": False,
                    "turn": turn,
                    "wall_s": round(time.perf_counter() - t0, 3),
                    "error": str(exc)[:400],
                    "outcome_hint": "exception",
                }
            )
            outcome = "exception"
            break

    summary = {
        "label": f"{catalog_id}/coding-max-ctx/summary",
        "model": run_name,
        "catalog_id": catalog_id,
        "ok": outcome
        in {
            "continued_ok_near_max",
            "hit_cap_continue_ok",
            "near_max_continue",
            "max_turns",
        }
        and any(r.get("ok") for r in rows),
        "outcome": outcome,
        # API path cannot see DSH UI compact; note for operators:
        "dsh_auto_compact": "not_observable_on_api_use_dsh_web_compact_flood",
        "can_continue_near_max": outcome
        in {"continued_ok_near_max", "hit_cap_continue_ok", "near_max_continue"},
        "turns": len([r for r in rows if "/turn-" in r.get("label", "")]),
        "last_prompt_tokens": next(
            (r.get("prompt_tokens") for r in reversed(rows) if r.get("prompt_tokens")),
            None,
        ),
        "context_cap": cap,
        "context_tokens_catalog": context_tokens,
    }
    rows.append(summary)
    return rows, n


def main() -> None:
    base = (
        os.environ.get("VAST_TEST_BASE_URL")
        or os.environ.get("LLM_STUDIO_TEST_BASE_URL")
        or ""
    ).rstrip("/")
    key = (
        os.environ.get("VAST_API_KEY")
        or os.environ.get("OPEN_BUTTON_TOKEN")
        or os.environ.get("LLM_STUDIO_API_KEY")
        or ""
    )
    if not base:
        fail("set VAST_TEST_BASE_URL or LLM_STUDIO_TEST_BASE_URL")

    specs = json.loads(CATALOG.read_text())["models"]
    filt = (
        os.environ.get("VAST_CYCLE_MODELS")
        or os.environ.get("LLM_STUDIO_TEST_MODELS")
        or ""
    ).strip()
    if filt:
        want = {x.strip() for x in filt.split(",") if x.strip()}
        specs = [m for m in specs if m["id"] in want or m.get("alias") in want]

    use_ollama = "11434" in base or os.environ.get("CODING_CTX_USE_OLLAMA", "") == "1"
    max_turns = int(os.environ.get("CODING_CTX_MAX_TURNS", "40"))
    # rough upper bound for progress display
    total = max(1, len(specs) * (max_turns + 1))
    n = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("")
    all_rows: list[dict] = []

    for spec in specs:
        mid = spec["id"]
        if use_ollama:
            run_name = ollama_tag(spec)
        else:
            if spec.get("deployment") == "vast-ollama":
                print(f"skip {mid}: vast-only on local API", flush=True)
                continue
            run_name = mid
        # Per-model max only — never a shared CODING_CTX_OLLAMA_CTX clamp
        ctx = test_context_tokens(spec)
        print(f"\n=== coding-agent max-ctx: {mid} as {run_name} (ctx_cap_base={ctx}) ===", flush=True)
        rows, n = run_model(
            base=base,
            key=key,
            catalog_id=mid,
            run_name=run_name,
            context_tokens=ctx,
            n_start=n,
            total=total,
        )
        for row in rows:
            all_rows.append(row)
            with OUT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    summaries = [r for r in all_rows if r.get("label", "").endswith("/summary")]
    print(
        json.dumps(
            {
                "wrote": str(OUT),
                "models": len(summaries),
                "rows": len(all_rows),
                "outcomes": {s["catalog_id"]: s.get("outcome") for s in summaries},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
