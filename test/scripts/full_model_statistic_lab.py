#!/usr/bin/env python3
"""Per-model statistic lab for local llm-studio catalog entries.

Deploys one model at a time via chat (resident switch), runs short/long/cache/
OCR/vision/concurrency probes, records metrics JSONL. Progress: N/M.

Env:
  LLM_STUDIO_API_KEY (required)
  LLM_STUDIO_TEST_BASE_URL (default http://10.8.0.1:18080/v1)
  LLM_STUDIO_TEST_MODELS (optional comma filter of catalog ids)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
ROOT = _SCRIPTS.parents[1]
sys.path.insert(0, str(_SCRIPTS))

from prompt_builders import approx_token_filler  # noqa: E402

CATALOG = ROOT / "configs" / "models.json"
OUT_DEFAULT = ROOT / "docs" / "perf-results" / "all-models-full-lab.jsonl"
OCR_ROOT = Path(os.environ.get("LLM_STUDIO_OCR_ROOT", "/home/tringuyen/Documents/Work/test docs/OCR"))
VISION_CANDIDATES = [
    Path("/home/tringuyen/Documents/tmp/apple.jpg"),
    OCR_ROOT / "tired_man_test.png",
    OCR_ROOT / "tired_man_test.jpg",
]


def fail(msg: str) -> None:
    raise SystemExit(f"full lab failed: {msg}")


def local_models() -> list[dict]:
    data = json.loads(CATALOG.read_text())
    models = []
    for m in data["models"]:
        if m.get("deployment", "local") != "local":
            continue
        models.append(m)
    filt = os.environ.get("LLM_STUDIO_TEST_MODELS", "").strip()
    if filt:
        want = {x.strip() for x in filt.split(",") if x.strip()}
        models = [m for m in models if m["id"] in want]
    return models


def request_json(url: str, key: str, body: dict | None = None, headers: dict | None = None, timeout: int = 900):
    hdrs = {"Authorization": f"Bearer {key}", **(headers or {})}
    data = None
    if body is not None:
        hdrs["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.load(resp), {k.lower(): v for k, v in resp.headers.items()}


def chat(base: str, key: str, model: str, messages: list, *, max_tokens: int, label: str, n: int, m: int, session: str) -> dict:
    print(f"running test case {n}/{m}: {label}", flush=True)
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "reasoning_effort": "off",
        "stream": False,
    }
    t0 = time.perf_counter()
    try:
        status, payload, headers = request_json(
            f"{base}/chat/completions",
            key,
            body,
            headers={"X-Session-ID": session, "X-Correlation-ID": f"{session}-{label}"},
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        return {"label": label, "model": model, "ok": False, "http_status": exc.code, "error": detail}
    except Exception as exc:  # noqa: BLE001
        return {"label": label, "model": model, "ok": False, "error": str(exc)[:300]}
    wall = round(time.perf_counter() - t0, 3)
    usage = payload.get("usage") or {}
    msg = (payload.get("choices") or [{}])[0].get("message") or {}
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens")
    prompt_tokens = usage.get("prompt_tokens") or 0
    cache_pct = None
    if prompt_tokens and cached is not None:
        cache_pct = round(cached / prompt_tokens * 100, 2)
    elif headers.get("x-cache-hit-percent") is not None:
        try:
            cache_pct = float(headers["x-cache-hit-percent"])
        except ValueError:
            cache_pct = headers.get("x-cache-hit-percent")
    return {
        "label": label,
        "model": model,
        "ok": status == 200,
        "http_status": status,
        "wall_s": wall,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": usage.get("completion_tokens"),
        "cached_tokens": cached,
        "cache_hit_percent": cache_pct,
        "first_token_ms": headers.get("x-first-token-ms"),
        "last_token_ms": headers.get("x-last-token-ms"),
        "kv_cache": headers.get("x-kv-cache"),
        "content_preview": (msg.get("content") or "")[:100],
        "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason"),
    }


def vision_path() -> Path | None:
    for p in VISION_CANDIDATES:
        if p.is_file():
            return p
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--long-tokens", type=int, default=2000, help="approx prompt filler for long case")
    parser.add_argument("--skip-vision", action="store_true")
    parser.add_argument("--skip-ocr", action="store_true")
    args = parser.parse_args()

    base = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://10.8.0.1:18080/v1").rstrip("/")
    key = os.environ.get("LLM_STUDIO_API_KEY", "")
    if not key:
        fail("set LLM_STUDIO_API_KEY")

    models = local_models()
    if not models:
        fail("no local catalog models")

    # cases per model: short, long, cache-cold, cache-warm, ocr?, vision?, concurrency
    rows: list[dict] = []
    # estimate M
    per = 5  # short long cachex2 concurrency
    total = 0
    for m in models:
        total += per
        if not args.skip_ocr:
            total += 1
        if m.get("vision") and not args.skip_vision:
            total += 1

    n = 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # truncate out at start
    args.out.write_text("")

    def append(row: dict) -> None:
        rows.append(row)
        with args.out.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    for spec in models:
        mid = spec["id"]
        session = f"full-lab-{spec['alias']}"
        print(f"=== deploy/switch model {mid} ===", flush=True)

        n += 1
        append(
            chat(
                base,
                key,
                mid,
                [{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=16,
                label=f"{mid}/short",
                n=n,
                m=total,
                session=session,
            )
        )

        n += 1
        long_msg = approx_token_filler(args.long_tokens) + "\n\nReply with exactly: LONG_OK"
        append(
            chat(
                base,
                key,
                mid,
                [{"role": "user", "content": long_msg}],
                max_tokens=16,
                label=f"{mid}/long-{args.long_tokens}",
                n=n,
                m=total,
                session=f"{session}-long",
            )
        )

        warm = [
            {"role": "system", "content": "Stable cache prefix. VPN API 10.8.0.1:18080."},
            {"role": "user", "content": "Reply with exactly: PONG"},
        ]
        n += 1
        append(
            chat(base, key, mid, warm, max_tokens=16, label=f"{mid}/cache-cold", n=n, m=total, session=f"{session}-cache")
        )
        n += 1
        append(
            chat(base, key, mid, warm, max_tokens=16, label=f"{mid}/cache-warm", n=n, m=total, session=f"{session}-cache")
        )

        if not args.skip_ocr:
            md = OCR_ROOT / "message.md"
            if md.is_file():
                n += 1
                text = md.read_text(encoding="utf-8", errors="replace")[:4000]
                row = chat(
                    base,
                    key,
                    mid,
                    [
                        {
                            "role": "user",
                            "content": f"Document:\n{text}\n\nWhat city? One short sentence.",
                        }
                    ],
                    max_tokens=64,
                    label=f"{mid}/ocr-md",
                    n=n,
                    m=total,
                    session=f"{session}-ocr",
                )
                row["accuracy_city"] = "Ho Chi Minh" in (row.get("content_preview") or "")
                append(row)

        if spec.get("vision") and not args.skip_vision:
            img = vision_path()
            if img is not None:
                n += 1
                b64 = base64.b64encode(img.read_bytes()).decode()
                mime = "image/jpeg" if img.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
                append(
                    chat(
                        base,
                        key,
                        mid,
                        [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "Main object in one short sentence."},
                                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                                ],
                            }
                        ],
                        max_tokens=64,
                        label=f"{mid}/vision",
                        n=n,
                        m=total,
                        session=f"{session}-vision",
                    )
                )

        n += 1
        print(f"running test case {n}/{total}: {mid}/concurrency-2", flush=True)

        def one(i: int) -> dict:
            return chat(
                base,
                key,
                mid,
                [{"role": "user", "content": f"Reply with exactly: C{i}"}],
                max_tokens=8,
                label=f"{mid}/concurrency-{i}",
                n=n,
                m=total,
                session=f"{session}-c{i}",
            )

        conc = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            for fut in as_completed([pool.submit(one, i) for i in (1, 2)]):
                conc.append(fut.result())
        append(
            {
                "label": f"{mid}/concurrency-2",
                "model": mid,
                "ok": all(r.get("ok") for r in conc),
                "walls": [r.get("wall_s") for r in conc],
                "note": "API max_concurrent often 1 — expect queue",
                "results": conc,
            }
        )

        print(f"=== cleanup hint: idle unload will drop {mid} after MODEL_IDLE_UNLOAD_SECONDS ===", flush=True)

    ok = sum(1 for r in rows if r.get("ok"))
    print(json.dumps({"wrote": str(args.out), "rows": len(rows), "ok": ok, "models": len(models)}, indent=2))


if __name__ == "__main__":
    main()
