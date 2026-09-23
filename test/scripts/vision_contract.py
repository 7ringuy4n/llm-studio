#!/usr/bin/env python3
"""Vision lab: simple + complicated real-world images for every vision-capable model.

Uses embedded PNG data URLs only. Progress: running test case N/M.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VISION_MODELS = (
    "Qwen/Qwen3.5-0.8B",
    "Qwen/Qwen3.5-2B",
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "vision"

CASES = (
    ("simple_color_panels", "simple-color-panels.png", "How many distinct color panels are visible? Reply with one number."),
    ("simple_object_mug", "simple-object-mug.png", "What single everyday object sits on the desk? Reply with one word."),
    (
        "complicated_nature_wallpaper",
        "complicated-nature-wallpaper.png",
        "Describe the scene in one sentence (sky, land/water, vegetation).",
    ),
    (
        "complicated_desk_scene",
        "complicated-desk-scene.png",
        "List three objects you can see on or near the desk, comma-separated.",
    ),
)


def fail(message: str) -> None:
    raise SystemExit(f"vision contract failed: {message}")


def data_url(path: Path) -> str:
    raw = path.read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}"


def chat_vision(
    *,
    base_url: str,
    api_key: str,
    model: str,
    image_path: Path,
    prompt: str,
    label: str,
    case_n: int,
    case_total: int,
) -> dict:
    print(f"running test case {case_n}/{case_total}: {label}", flush=True)
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url(image_path)}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 96,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Session-ID": f"vision-{label}",
            "X-Correlation-ID": f"vision-{label}",
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
    content = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if status != 200 or not content.strip():
        fail(f"{label}: status={status} empty={not content.strip()}")
    row = {
        "model": model,
        "case": label,
        "image": image_path.name,
        "wall_ms": wall_ms,
        "first_token_ms": headers.get("x-first-token-ms") or headers.get("x-first-token-latency-ms"),
        "answer_preview": content.strip()[:200],
    }
    print(f"  ok wall_ms={wall_ms} preview={row['answer_preview'][:80]!r}", flush=True)
    return row


def main() -> None:
    base_url = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://10.8.0.1:18080/v1").rstrip("/")
    api_key = os.environ.get("LLM_STUDIO_API_KEY", "")
    if not api_key:
        fail("set LLM_STUDIO_API_KEY without printing it")
    models_raw = os.environ.get("LLM_STUDIO_VISION_MODELS", "").strip()
    models = (
        [m.strip() for m in models_raw.split(",") if m.strip()]
        if models_raw
        else list(VISION_MODELS)
    )
    for _, filename, _ in CASES:
        path = FIXTURES / filename
        if not path.is_file():
            fail(f"missing fixture {path}")

    case_total = len(models) * len(CASES)
    case_n = 0
    rows: list[dict] = []
    for model in models:
        for key, filename, prompt in CASES:
            case_n += 1
            rows.append(
                chat_vision(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    image_path=FIXTURES / filename,
                    prompt=prompt,
                    label=f"{model}::{key}",
                    case_n=case_n,
                    case_total=case_total,
                )
            )

    out = Path(__file__).resolve().parents[1] / "reports" / "vision-perf.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": rows}, indent=2) + "\n")
    print(f"wrote {out}", flush=True)
    print(f"vision contract PASS: {case_total}/{case_total}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
