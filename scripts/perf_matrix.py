#!/usr/bin/env python3
"""CPU performance matrix for llm-studio (matches model-statistic 2.docx shape).

Measures, for each living model × reasoning_effort:
  tokens in/out, first-token ms, last-token ms, wall total, cache hit %,
  math correctness (15+32=47), exact FINAL=47 format.

Also runs a two-shot prefix-cache probe on the first GGUF model.

Usage:
  LLM_STUDIO_API_KEY=... LLM_STUDIO_TEST_BASE_URL=http://10.8.0.1:18080/v1 \\
    python3 scripts/perf_matrix.py --label cpus3 --out /tmp/perf-cpus3.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


MODELS = [
    "Qwen/Qwen3.5-0.8B",
    "Qwen/Qwen3.5-2B",
    "Qwen/Qwen3-8B",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "meta-llama/Llama-3.1-8B-Instruct",
]
EFFORTS = ["off", "low", "medium", "high", "xhigh", "max"]
PROMPT = (
    "A store sold 15 apples in the morning and 32 in the afternoon. "
    "How many apples were sold in total?\n"
    "Reply with exactly one line: FINAL=<number>\n"
    "No other text."
)
EXPECTED = 47


def _request(
    base_url: str,
    api_key: str,
    model: str,
    effort: str,
    max_tokens: int,
    timeout: float,
    *,
    retries: int = 4,
) -> dict[str, object]:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "reasoning_effort": effort,
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Session-ID": f"perf-{model}-{effort}",
                "X-Correlation-ID": "perf-matrix",
            },
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.load(resp)
                headers = {k.lower(): v for k, v in resp.headers.items()}
            wall_s = time.monotonic() - started
            return {"payload": payload, "headers": headers, "wall_s": wall_s}
        except urllib.error.HTTPError as exc:
            body_txt = exc.read().decode(errors="replace")[:240]
            last_error = RuntimeError(f"HTTP {exc.code}: {body_txt}")
            if exc.code in {502, 503, 504} and attempt < retries:
                print(f"  retry {attempt}/{retries} after HTTP {exc.code}", flush=True)
                time.sleep(min(45, 8 * attempt))
                continue
            raise last_error from exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < retries:
                print(f"  retry {attempt}/{retries} after {exc}", flush=True)
                time.sleep(min(45, 8 * attempt))
                continue
            raise
    assert last_error is not None
    raise last_error


def _score(text: str) -> tuple[bool, bool]:
    nums = [int(x) for x in re.findall(r"-?\d+", text or "")]
    math_ok = EXPECTED in nums
    exact = bool(re.search(rf"(?m)^FINAL\s*=\s*{EXPECTED}\s*$", text or ""))
    return math_ok, exact


def _row(
    label: str,
    model: str,
    effort: str,
    result: dict[str, object] | None,
    error: str | None,
) -> dict[str, object]:
    if error or result is None:
        return {
            "label": label,
            "model": model,
            "effort": effort,
            "ok": False,
            "error": error,
        }
    payload = result["payload"]  # type: ignore[index]
    headers = result["headers"]  # type: ignore[index]
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    text = message.get("content") or ""
    reasoning = message.get("reasoning_content") or ""
    usage = payload.get("usage") or {}
    details = usage.get("prompt_tokens_details") or {}
    math_ok, exact = _score(text)
    first_ms = float(headers.get("x-first-token-ms") or 0)
    last_ms = float(headers.get("x-last-token-ms") or 0)
    return {
        "label": label,
        "model": model,
        "effort": effort,
        "ok": True,
        "http_status": 200,
        "finish_reason": choice.get("finish_reason"),
        "math_ok": math_ok,
        "exact_format": exact,
        "tokens_in": usage.get("prompt_tokens"),
        "tokens_out": usage.get("completion_tokens"),
        "cached_tokens": details.get("cached_tokens", 0),
        "cache_hit_percent": float(headers.get("x-cache-hit-percent") or 0),
        "first_token_s": round(first_ms / 1000.0, 3) if first_ms else None,
        "last_token_s": round(last_ms / 1000.0, 3) if last_ms else None,
        "total_s": round(float(result["wall_s"]), 3),  # type: ignore[arg-type]
        "answer_preview": (text or "")[:160],
        "reasoning_chars": len(reasoning),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True, help="run label, e.g. cpus3 / cpus4")
    parser.add_argument("--out", required=True, help="JSONL output path")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument(
        "--efforts",
        default=",".join(EFFORTS),
        help="comma list of reasoning_effort values",
    )
    parser.add_argument(
        "--models",
        default=",".join(MODELS),
        help="comma list of model ids",
    )
    parser.add_argument(
        "--cache-probe",
        action="store_true",
        help="after matrix, repeat one GGUF request to measure prefix cache",
    )
    parser.add_argument(
        "--pause-between-models",
        type=float,
        default=8.0,
        help="seconds to sleep when the model id changes (lets unload settle)",
    )
    parser.add_argument(
        "--only-missing-from",
        default="",
        help="JSONL path: skip model/effort pairs that already succeeded there",
    )
    args = parser.parse_args()

    base_url = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://127.0.0.1:18080/v1")
    api_key = os.environ.get("LLM_STUDIO_API_KEY", "")
    if len(api_key) < 32:
        print("set LLM_STUDIO_API_KEY", file=sys.stderr)
        return 2

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    efforts = [e.strip() for e in args.efforts.split(",") if e.strip()]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    skip: set[tuple[str, str]] = set()
    if args.only_missing_from:
        for line in Path(args.only_missing_from).read_text().splitlines():
            if not line.strip():
                continue
            prev = json.loads(line)
            if prev.get("ok") and not str(prev.get("effort", "")).startswith("cache"):
                skip.add((prev["model"], prev["effort"]))

    rows: list[dict[str, object]] = []
    prev_model: str | None = None
    with out.open("a" if skip else "w", encoding="utf-8") as fh:
        for model in models:
            if prev_model is not None and model != prev_model and args.pause_between_models > 0:
                print(f"pause {args.pause_between_models}s before switching model", flush=True)
                time.sleep(args.pause_between_models)
            prev_model = model
            for effort in efforts:
                if (model, effort) in skip:
                    print(f"[{args.label}] skip existing OK {model} effort={effort}", flush=True)
                    continue
                print(f"[{args.label}] {model} effort={effort}", flush=True)
                try:
                    result = _request(
                        base_url, api_key, model, effort, args.max_tokens, args.timeout
                    )
                    row = _row(args.label, model, effort, result, None)
                except urllib.error.HTTPError as exc:
                    row = _row(
                        args.label,
                        model,
                        effort,
                        None,
                        f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:240]}",
                    )
                except Exception as exc:  # noqa: BLE001 - bench must continue
                    row = _row(args.label, model, effort, None, str(exc))
                rows.append(row)
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                status = "OK" if row.get("ok") else f"ERR {row.get('error')}"
                print(
                    f"  -> {status} in/out={row.get('tokens_in')}/{row.get('tokens_out')} "
                    f"first={row.get('first_token_s')}s last={row.get('last_token_s')}s "
                    f"total={row.get('total_s')}s cache%={row.get('cache_hit_percent')} "
                    f"math={row.get('math_ok')} exact={row.get('exact_format')}",
                    flush=True,
                )

        if args.cache_probe:
            gguf = next((m for m in models if "Qwen3-8B" in m or "Llama" in m or "DeepSeek" in m), models[-1])
            print(f"[{args.label}] cache probe on {gguf}", flush=True)
            for i in range(2):
                try:
                    result = _request(
                        base_url, api_key, gguf, "off", 32, args.timeout
                    )
                    row = _row(args.label, gguf, f"cache_probe_{i+1}", result, None)
                except Exception as exc:  # noqa: BLE001
                    row = _row(args.label, gguf, f"cache_probe_{i+1}", None, str(exc))
                rows.append(row)
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                print(
                    f"  probe{i+1}: cache%={row.get('cache_hit_percent')} "
                    f"cached={row.get('cached_tokens')} first={row.get('first_token_s')}s",
                    flush=True,
                )

    ok = sum(1 for r in rows if r.get("ok"))
    math = sum(1 for r in rows if r.get("math_ok"))
    exact = sum(1 for r in rows if r.get("exact_format"))
    print(
        f"DONE label={args.label} rows={len(rows)} ok={ok} math={math} exact={exact} out={out}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
