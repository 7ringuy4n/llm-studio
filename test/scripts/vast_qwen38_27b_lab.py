#!/usr/bin/env python3
"""Vast GPU lab for catalog vast-ollama models (Qwen3.8-27B).

Runs against Ollama OpenAI-compatible API on Vast.
Progress: running test case N/M. Does not print secrets.
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
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from prompt_builders import approx_token_filler  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "configs" / "models.json"
OUT_DEFAULT = ROOT / "docs" / "perf-results" / "vast-qwen38-27b-lab.jsonl"
OCR_ROOT = Path(os.environ.get("LLM_STUDIO_OCR_ROOT", "/home/tringuyen/Documents/Work/test docs/OCR"))
VISION_IMG = Path("/home/tringuyen/Documents/tmp/apple.jpg")
if not VISION_IMG.is_file():
    VISION_IMG = OCR_ROOT / "tired_man_test.png"


def fail(msg: str) -> None:
    raise SystemExit(f"vast lab failed: {msg}")


def vast_targets() -> list[dict]:
    data = json.loads(CATALOG.read_text())
    out = []
    for m in data.get("models", []):
        if m.get("deployment") == "vast-ollama":
            out.append(m)
    return out


def chat(
    *,
    base: str,
    key: str,
    model: str,
    messages: list,
    max_tokens: int,
    label: str,
    case_n: int,
    case_total: int,
    session: str,
    temperature: float = 0,
) -> dict:
    print(f"running test case {case_n}/{case_total}: {label}", flush=True)
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{base.rstrip('/')}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "X-Session-ID": session,
            "X-Correlation-ID": f"{session}-{label}",
        },
        method="POST",
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            payload = json.load(resp)
            headers = {k.lower(): v for k, v in resp.headers.items()}
            status = resp.status
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:800]
        fail(f"{label}: HTTP {exc.code}: {detail}")
    except urllib.error.URLError as exc:
        fail(f"{label}: {exc.reason}")
    wall = round(time.perf_counter() - t0, 3)
    msg = (payload.get("choices") or [{}])[0].get("message") or {}
    usage = payload.get("usage") or {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning") or msg.get("reasoning_content") or ""
    return {
        "label": label,
        "model": model,
        "ok": status == 200,
        "http_status": status,
        "wall_s": wall,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "cache_hit_percent": headers.get("x-cache-hit-percent"),
        "first_token_ms": headers.get("x-first-token-ms"),
        "content_preview": (content or "")[:120],
        "reasoning_preview": (reasoning or "")[:120],
        "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    args = parser.parse_args()

    base = os.environ.get("VAST_TEST_BASE_URL", "").rstrip("/")
    key = os.environ.get("VAST_API_KEY") or os.environ.get("OPEN_BUTTON_TOKEN") or ""
    if not base:
        fail("set VAST_TEST_BASE_URL to the instance OpenAI base (.../v1); do not hardcode host:port in repo")
    if not key:
        fail("set VAST_API_KEY (Vast OPEN_BUTTON_TOKEN)")

    targets = vast_targets()
    if not targets:
        fail("no vast-ollama entries in configs/models.json")

    rows: list[dict] = []
    # Approximate case count: per model ~10 cases
    total = len(targets) * 10
    n = 0

    for spec in targets:
        ollama = spec["ollama_model"]
        catalog_id = spec["id"]
        session = f"vast-lab-{spec['alias']}"

        # 1 short
        n += 1
        rows.append(
            chat(
                base=base,
                key=key,
                model=ollama,
                messages=[{"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=64,
                label=f"{catalog_id}/short",
                case_n=n,
                case_total=total,
                session=session,
            )
        )

        # 2-3 cache warm (same prompt twice)
        warm_msgs = [
            {
                "role": "system",
                "content": "Stable prefix for cache probe. Homelab API 10.8.0.1:18080.",
            },
            {"role": "user", "content": "Reply with exactly: PONG"},
        ]
        n += 1
        rows.append(
            chat(
                base=base,
                key=key,
                model=ollama,
                messages=warm_msgs,
                max_tokens=32,
                label=f"{catalog_id}/cache-cold",
                case_n=n,
                case_total=total,
                session=f"{session}-cache",
            )
        )
        n += 1
        rows.append(
            chat(
                base=base,
                key=key,
                model=ollama,
                messages=warm_msgs,
                max_tokens=32,
                label=f"{catalog_id}/cache-warm",
                case_n=n,
                case_total=total,
                session=f"{session}-cache",
            )
        )

        # 4 medium long (~2k tokens — stay inside disk/VRAM comfort)
        n += 1
        long_user = approx_token_filler(2000) + "\n\nReply with exactly: LONG_OK"
        rows.append(
            chat(
                base=base,
                key=key,
                model=ollama,
                messages=[{"role": "user", "content": long_user}],
                max_tokens=32,
                label=f"{catalog_id}/long-2k",
                case_n=n,
                case_total=total,
                session=f"{session}-long",
            )
        )

        # 5 longer (~8k)
        n += 1
        long8 = approx_token_filler(8000) + "\n\nReply with exactly: LONG8_OK"
        rows.append(
            chat(
                base=base,
                key=key,
                model=ollama,
                messages=[{"role": "user", "content": long8}],
                max_tokens=32,
                label=f"{catalog_id}/long-8k",
                case_n=n,
                case_total=total,
                session=f"{session}-long8",
            )
        )

        # 6 OCR grounded (md extract)
        md = OCR_ROOT / "message.md"
        if md.is_file():
            n += 1
            text = md.read_text(encoding="utf-8", errors="replace")[:6000]
            rows.append(
                chat(
                    base=base,
                    key=key,
                    model=ollama,
                    messages=[
                        {
                            "role": "user",
                            "content": (
                                "Document extract:\n"
                                + text
                                + "\n\nWhat city is this weather update for? One short sentence."
                            ),
                        }
                    ],
                    max_tokens=128,
                    label=f"{catalog_id}/ocr-md",
                    case_n=n,
                    case_total=total,
                    session=f"{session}-ocr",
                )
            )
            preview = (rows[-1].get("content_preview") or "") + (
                rows[-1].get("reasoning_preview") or ""
            )
            rows[-1]["accuracy_city"] = "Ho Chi Minh" in preview or "Hochiminh" in preview.replace(
                " ", ""
            )

        # 7 vision
        if spec.get("vision") and VISION_IMG.is_file():
            n += 1
            b64 = base64.b64encode(VISION_IMG.read_bytes()).decode()
            mime = "image/jpeg" if VISION_IMG.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            rows.append(
                chat(
                    base=base,
                    key=key,
                    model=ollama,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Describe the main object in one short sentence.",
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                                },
                            ],
                        }
                    ],
                    max_tokens=128,
                    label=f"{catalog_id}/vision",
                    case_n=n,
                    case_total=total,
                    session=f"{session}-vision",
                )
            )

        # 8 concurrency (2 parallel shorts)
        n += 1
        print(f"running test case {n}/{total}: {catalog_id}/concurrency-2", flush=True)

        def _one(i: int) -> dict:
            return chat(
                base=base,
                key=key,
                model=ollama,
                messages=[{"role": "user", "content": f"Reply with exactly: C{i}"}],
                max_tokens=32,
                label=f"{catalog_id}/concurrency-{i}",
                case_n=n,
                case_total=total,
                session=f"{session}-c{i}",
            )

        conc: list[dict] = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futs = [pool.submit(_one, i) for i in (1, 2)]
            for fut in as_completed(futs):
                try:
                    conc.append(fut.result())
                except SystemExit as exc:
                    conc.append({"ok": False, "error": str(exc)})
        rows.append(
            {
                "label": f"{catalog_id}/concurrency-2",
                "model": ollama,
                "ok": all(r.get("ok") for r in conc),
                "walls": [r.get("wall_s") for r in conc],
                "results": conc,
            }
        )

        # 9 tool-ish: ask to call a fake tool schema if API accepts tools
        n += 1
        print(f"running test case {n}/{total}: {catalog_id}/tools-web_search", flush=True)
        body = {
            "model": ollama,
            "messages": [
                {
                    "role": "user",
                    "content": "Use web_search exactly once for OpenObserve GitHub, then stop.",
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "description": "Search the web",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    },
                }
            ],
            "tool_choice": "required",
            "max_tokens": 128,
            "temperature": 0,
        }
        req = urllib.request.Request(
            f"{base.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "X-Session-ID": f"{session}-tools",
            },
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                payload = json.load(resp)
            msg = (payload.get("choices") or [{}])[0].get("message") or {}
            calls = msg.get("tool_calls") or []
            rows.append(
                {
                    "label": f"{catalog_id}/tools-web_search",
                    "model": ollama,
                    "ok": True,
                    "wall_s": round(time.perf_counter() - t0, 3),
                    "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason"),
                    "tool_calls": len(calls),
                    "content_preview": (msg.get("content") or "")[:80],
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "label": f"{catalog_id}/tools-web_search",
                    "model": ollama,
                    "ok": False,
                    "error": str(exc)[:300],
                }
            )

        # 10 fill remaining progress slots if under-counted
        while n < total and n < len(targets) * 10:
            n += 1
            print(f"running test case {n}/{total}: {catalog_id}/pad-skip", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    ok = sum(1 for r in rows if r.get("ok"))
    print(json.dumps({"wrote": str(args.out), "rows": len(rows), "ok": ok}, indent=2))
    if ok < len(rows):
        fail(f"only {ok}/{len(rows)} cases ok")


if __name__ == "__main__":
    main()
