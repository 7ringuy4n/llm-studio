#!/usr/bin/env python3
"""API coding simulation cases per living model (lab-temp §8).

Progress: running test case N/M
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "configs" / "models.json"
OUT = ROOT / "docs" / "perf-results" / "coding-sim-lab.jsonl"

CASES = [
    {
        "id": "add-fn",
        "prompt": (
            "Write only this exact line as the entire reply (no fences, no prose):\n"
            "return a + b"
        ),
        "expect": re.compile(r"return a \+ b"),
    },
    {
        "id": "fizz-fix",
        "prompt": (
            "In one line of Python, assign to x the string 'fizz' if n is divisible by 3 else 'buzz'. "
            "Reply with ONLY: x = 'fizz' if n % 3 == 0 else 'buzz'"
        ),
        "expect": re.compile(r"x = 'fizz' if n % 3 == 0 else 'buzz'"),
    },
]


def fail(msg: str) -> None:
    raise SystemExit(f"coding sim failed: {msg}")


def request_json(url: str, key: str, body: dict, timeout: int = 600):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.load(resp), {k.lower(): v for k, v in resp.headers.items()}


def main() -> None:
    base = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://10.8.0.1:18080/v1").rstrip("/")
    key = os.environ.get("LLM_STUDIO_API_KEY", "")
    if not key:
        fail("set LLM_STUDIO_API_KEY")
    models = [
        m
        for m in json.loads(CATALOG.read_text())["models"]
        if m.get("deployment", "local") == "local"
    ]
    filt = os.environ.get("LLM_STUDIO_TEST_MODELS", "").strip()
    if filt:
        want = {x.strip() for x in filt.split(",") if x.strip()}
        models = [m for m in models if m["id"] in want]

    total = len(models) * len(CASES)
    n = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("")
    rows = []

    for spec in models:
        mid = spec["id"]
        print(f"=== deploy/switch model {mid} ===", flush=True)
        for case in CASES:
            n += 1
            label = f"{mid}/coding-{case['id']}"
            print(f"running test case {n}/{total}: {label}", flush=True)
            t0 = time.perf_counter()
            try:
                status, payload, headers = request_json(
                    f"{base}/chat/completions",
                    key,
                    {
                        "model": mid,
                        "messages": [{"role": "user", "content": case["prompt"]}],
                        "max_tokens": 64,
                        "temperature": 0,
                        "reasoning_effort": "off",
                        "stream": False,
                    },
                )
                content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                usage = payload.get("usage") or {}
                ok = status == 200 and bool(case["expect"].search(content))
                row = {
                    "label": label,
                    "ok": ok,
                    "http_status": status,
                    "wall_s": round(time.perf_counter() - t0, 3),
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "first_token_ms": headers.get("x-first-token-ms"),
                    "last_token_ms": headers.get("x-last-token-ms"),
                    "content_preview": content[:200],
                }
            except urllib.error.HTTPError as exc:
                row = {
                    "label": label,
                    "ok": False,
                    "http_status": exc.code,
                    "error": exc.read().decode(errors="replace")[:400],
                    "wall_s": round(time.perf_counter() - t0, 3),
                }
            except Exception as exc:  # noqa: BLE001
                row = {"label": label, "ok": False, "error": str(exc)[:400], "wall_s": round(time.perf_counter() - t0, 3)}
            rows.append(row)
            with OUT.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    ok = sum(1 for r in rows if r.get("ok"))
    print(json.dumps({"wrote": str(OUT), "rows": len(rows), "ok": ok}, indent=2))


if __name__ == "__main__":
    main()
