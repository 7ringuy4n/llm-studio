#!/usr/bin/env python3
"""Short → stepped → near-max context ladder per catalog model.

For each local (or filtered) model: deploy, then probe prompt sizes from short
up to min(context_tokens - max_new_tokens - margin, optional cap). Records
first/last token headers, cache%, wall, and host RSS/CPU samples via /proc
over SSH-less local scrape of VPN health + optional HOST_STATS_CMD.

Env:
  LLM_STUDIO_API_KEY (required for local)
  LLM_STUDIO_TEST_BASE_URL (default http://10.8.0.1:18080/v1)
  LLM_STUDIO_TEST_MODELS (optional comma ids)
  LLM_STUDIO_CTX_LADDER_CAP (optional hard cap tokens; default 28000)
  HOST_STATS_URL (optional JSON with cpu_pct / mem_used_gib)
Progress: running test case N/M
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
ROOT = _SCRIPTS.parents[1]
sys.path.insert(0, str(_SCRIPTS))

from prompt_builders import approx_token_filler  # noqa: E402

CATALOG = ROOT / "configs" / "models.json"
OUT_DEFAULT = ROOT / "docs" / "perf-results" / "context-max-ladder.jsonl"


def fail(msg: str) -> None:
    raise SystemExit(f"context ladder failed: {msg}")


def request_json(url: str, key: str, body: dict | None = None, timeout: int = 1800):
    hdrs = {"Authorization": f"Bearer {key}"}
    data = None
    if body is not None:
        hdrs["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.load(resp), {k.lower(): v for k, v in resp.headers.items()}


def host_stats() -> dict:
    """Best-effort host sample; never fails the lab."""
    out: dict = {}
    url = os.environ.get("HOST_STATS_URL", "").strip()
    if url:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                out["remote"] = json.load(resp)
        except Exception as exc:  # noqa: BLE001
            out["remote_error"] = str(exc)[:120]
    # Local operator machine (not VPS) — still useful as wall-clock companion.
    try:
        mem = Path("/proc/meminfo").read_text()
        vals = {}
        for line in mem.splitlines():
            if line.startswith(("MemTotal:", "MemAvailable:")):
                k, v, *_ = line.split()
                vals[k.rstrip(":")] = int(v) / (1024 * 1024)
        if "MemTotal" in vals and "MemAvailable" in vals:
            out["operator_mem_used_gib"] = round(vals["MemTotal"] - vals["MemAvailable"], 2)
            out["operator_mem_total_gib"] = round(vals["MemTotal"], 2)
    except OSError:
        pass
    return out


def ladder_sizes(context_tokens: int, max_new_tokens: int) -> list[int]:
    """Short → mid → near prompt-room max (catalog context − max_new − margin)."""
    margin = 256
    prompt_room = max(512, context_tokens - max_new_tokens - margin)
    cap = int(os.environ.get("LLM_STUDIO_CTX_LADDER_CAP", "28000"))
    target_max = min(prompt_room, cap)
    base = [64, 512, 2000, 8000, 16000, 24000, target_max]
    seen: set[int] = set()
    out: list[int] = []
    for n in base:
        n = min(n, target_max)
        if n not in seen and n > 0:
            seen.add(n)
            out.append(n)
    if target_max not in seen:
        out.append(target_max)
    return out


def chat(base: str, key: str, model: str, prompt_tokens_approx: int, *, n: int, m: int, session: str) -> dict:
    label = f"{model}/ctx-{prompt_tokens_approx}"
    print(f"running test case {n}/{m}: {label}", flush=True)
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": approx_token_filler(prompt_tokens_approx) + "\n\nReply with exactly: CTX_OK",
            }
        ],
        "max_tokens": 16,
        "temperature": 0,
        "reasoning_effort": "off",
        "stream": False,
    }
    t0 = time.perf_counter()
    stats = host_stats()
    try:
        status, payload, headers = request_json(
            f"{base}/chat/completions",
            key,
            body,
            timeout=1800,
        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:800]
        return {
            "label": label,
            "model": model,
            "ok": False,
            "approx_prompt_tokens": prompt_tokens_approx,
            "http_status": exc.code,
            "error": detail,
            "host": stats,
            "wall_s": round(time.perf_counter() - t0, 3),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "label": label,
            "model": model,
            "ok": False,
            "approx_prompt_tokens": prompt_tokens_approx,
            "error": str(exc)[:400],
            "host": stats,
            "wall_s": round(time.perf_counter() - t0, 3),
        }
    wall = round(time.perf_counter() - t0, 3)
    usage = payload.get("usage") or {}
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
    msg = (payload.get("choices") or [{}])[0].get("message") or {}
    return {
        "label": label,
        "model": model,
        "ok": status == 200,
        "http_status": status,
        "approx_prompt_tokens": prompt_tokens_approx,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": usage.get("completion_tokens"),
        "cached_tokens": cached,
        "cache_hit_percent": cache_pct,
        "first_token_ms": headers.get("x-first-token-ms"),
        "last_token_ms": headers.get("x-last-token-ms"),
        "kv_cache": headers.get("x-kv-cache"),
        "wall_s": wall,
        "content_preview": (msg.get("content") or "")[:80],
        "host": stats,
        "host_after": host_stats(),
    }


def models() -> list[dict]:
    data = json.loads(CATALOG.read_text())
    ms = [m for m in data["models"] if m.get("deployment", "local") == "local"]
    filt = os.environ.get("LLM_STUDIO_TEST_MODELS", "").strip()
    if filt:
        want = {x.strip() for x in filt.split(",") if x.strip()}
        ms = [m for m in ms if m["id"] in want]
    return ms


def main() -> None:
    base = os.environ.get("LLM_STUDIO_TEST_BASE_URL", "http://10.8.0.1:18080/v1").rstrip("/")
    key = os.environ.get("LLM_STUDIO_API_KEY", "")
    if not key:
        fail("set LLM_STUDIO_API_KEY")
    out_path = Path(os.environ.get("LLM_STUDIO_CTX_OUT", str(OUT_DEFAULT)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("")

    specs = models()
    sizes_by = {
        m["id"]: ladder_sizes(int(m["context_tokens"]), int(m["max_new_tokens"])) for m in specs
    }
    total = sum(len(v) for v in sizes_by.values())
    n = 0
    rows: list[dict] = []

    def append(row: dict) -> None:
        rows.append(row)
        with out_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    for spec in specs:
        mid = spec["id"]
        print(f"=== deploy/switch model {mid} (prompt_room ladder) ===", flush=True)
        session = f"ctx-ladder-{spec['alias']}"
        for size in sizes_by[mid]:
            n += 1
            row = chat(base, key, mid, size, n=n, m=total, session=session)
            row["catalog_context_tokens"] = spec["context_tokens"]
            row["catalog_max_new_tokens"] = spec["max_new_tokens"]
            row["prompt_room"] = spec["context_tokens"] - spec["max_new_tokens"]
            append(row)
            # Stop climbing this model after hard context exceed / OOM class errors
            err = (row.get("error") or "").lower()
            if not row.get("ok") and any(
                x in err for x in ("context", "too long", "oom", "out of memory", "exceed")
            ):
                print(f"=== stop ladder for {mid} after failure at ~{size} ===", flush=True)
                break

    ok = sum(1 for r in rows if r.get("ok"))
    print(json.dumps({"wrote": str(out_path), "rows": len(rows), "ok": ok, "models": len(specs)}, indent=2))


if __name__ == "__main__":
    main()
