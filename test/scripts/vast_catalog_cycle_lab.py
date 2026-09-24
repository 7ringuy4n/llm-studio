#!/usr/bin/env python3
"""Deploy each models.json entry on Vast Ollama, one at a time with cleanup.

Maps catalog IDs → Ollama pull tags. For each model:
  1) stop+rm previous  2) pull  3) warm  4) short lab  5) stop+rm
Progress: running test case N/M

Env:
  VAST_TEST_BASE_URL (required, e.g. http://127.0.0.1:11434/v1)
  VAST_API_KEY (optional; Ollama local often empty)
  VAST_SSH (default: -p 58164 root@159.48.242.16) — used only for pull/rm via SSH
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
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
OUT = ROOT / "docs" / "perf-results" / "vast-all-models-cycle.jsonl"
OCR_ROOT = Path(os.environ.get("LLM_STUDIO_OCR_ROOT", "/home/tringuyen/Documents/Work/test docs/OCR"))
OCR_MD = OCR_ROOT / "message.md"
VISION_IMG = Path("/home/tringuyen/Documents/tmp/apple.jpg")
if not VISION_IMG.is_file():
    VISION_IMG = OCR_ROOT / "tired_man_test.png"

# Catalog id → ollama pull name (one-at-a-time to fit ≤32GB disk)
OLLAMA_MAP = {
    "Qwen/Qwen3.5-0.8B": "qwen3.5:0.8b",
    "Qwen/Qwen3.5-2B": "qwen3.5:2b",
    "Qwen/Qwen3.5-4B": "qwen3.5:4b",
    "Qwen/Qwen3.5-9B": "qwen3.5:9b",
    "Qwen/Qwen3-1.7B": "qwen3:1.7b",
    "Qwen/Qwen3-8B": "qwen3:8b",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek-r1:7b",
    "meta-llama/Llama-3.1-8B-Instruct": "llama3.1:8b",
    "Qwen/Qwen3.8-27B": "qwen3.8:27b",
}

SSH_TARGET = os.environ.get("VAST_SSH", "root@50.217.254.165")
SSH_PORT = os.environ.get("VAST_SSH_PORT", "40235")


def fail(msg: str) -> None:
    raise SystemExit(f"vast cycle failed: {msg}")


def ssh(cmd: str, timeout: int = 3600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            "-p",
            SSH_PORT,
            SSH_TARGET,
            cmd,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def remote(cmd: str, timeout: int = 3600) -> str:
    r = ssh(cmd, timeout=timeout)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-800:]
        raise RuntimeError(f"ssh rc={r.returncode}: {err}")
    return r.stdout


def cleanup_all() -> None:
    print("=== cleanup: stop+rm all ollama models ===", flush=True)
    remote(
        "for n in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop \"$n\" 2>/dev/null || true; done; "
        "for n in $(ollama list 2>/dev/null | awk 'NR>1{print $1}'); do ollama rm \"$n\" 2>/dev/null || true; done; "
        "df -h / | tail -1; ollama list; "
        "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null || true",
        timeout=600,
    )


def pull(tag: str) -> None:
    print(f"=== pull {tag} ===", flush=True)
    # stream progress via remote; may take long for 27b
    r = ssh(f"ollama pull {tag}", timeout=7200)
    # pull prints to stderr often
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        raise RuntimeError(f"pull {tag} failed: {out[-800:]}")
    print(out[-400:], flush=True)


def ensure_ctx64k(base_tag: str, alias: str, num_ctx: int = 65536) -> str:
    """Create Modelfile alias with num_ctx for large models."""
    remote(
        f"printf '%s\\n' 'FROM {base_tag}' 'PARAMETER num_ctx {num_ctx}' > /tmp/Modelfile.ctx && "
        f"ollama create {alias} -f /tmp/Modelfile.ctx && ollama list | head -20",
        timeout=600,
    )
    return alias


def request_json(url: str, key: str, body: dict | None = None, timeout: int = 600):
    hdrs = {}
    if key:
        hdrs["Authorization"] = f"Bearer {key}"
    data = None
    if body is not None:
        hdrs["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.load(resp), {k.lower(): v for k, v in resp.headers.items()}


def gpu_stats() -> dict:
    try:
        out = remote(
            "nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu "
            "--format=csv,noheader,nounits",
            timeout=30,
        ).strip()
        parts = [p.strip() for p in out.split(",")]
        return {
            "vram_used_mib": int(float(parts[0])),
            "vram_total_mib": int(float(parts[1])),
            "gpu_util_pct": int(float(parts[2])) if len(parts) > 2 else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:120]}


def chat(base: str, key: str, model: str, messages: list, *, max_tokens: int, label: str, n: int, m: int) -> dict:
    print(f"running test case {n}/{m}: {label}", flush=True)
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "stream": False,
    }
    t0 = time.perf_counter()
    host = gpu_stats()
    try:
        status, payload, headers = request_json(f"{base}/chat/completions", key, body, timeout=900)
    except urllib.error.HTTPError as exc:
        return {
            "label": label,
            "model": model,
            "ok": False,
            "http_status": exc.code,
            "error": exc.read().decode(errors="replace")[:500],
            "wall_s": round(time.perf_counter() - t0, 3),
            "gpu": host,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "label": label,
            "model": model,
            "ok": False,
            "error": str(exc)[:400],
            "wall_s": round(time.perf_counter() - t0, 3),
            "gpu": host,
        }
    usage = payload.get("usage") or {}
    msg = (payload.get("choices") or [{}])[0].get("message") or {}
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens")
    prompt_tokens = usage.get("prompt_tokens") or 0
    cache_pct = round(cached / prompt_tokens * 100, 2) if prompt_tokens and cached is not None else None
    return {
        "label": label,
        "model": model,
        "ok": status == 200,
        "http_status": status,
        "wall_s": round(time.perf_counter() - t0, 3),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": usage.get("completion_tokens"),
        "cached_tokens": cached,
        "cache_hit_percent": cache_pct,
        "content_preview": (msg.get("content") or "")[:160],
        "finish_reason": (payload.get("choices") or [{}])[0].get("finish_reason"),
        "gpu": host,
        "gpu_after": gpu_stats(),
    }


def run_model_suite(base: str, key: str, catalog_id: str, run_name: str, vision: bool, n_start: int, total: int) -> tuple[list[dict], int]:
    """Full suite: short, cache×2, long 2k/8k, OCR, vision?, coding, concurrency."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    rows: list[dict] = []
    n = n_start

    def one(label: str, messages: list, max_tokens: int = 32) -> dict:
        nonlocal n
        n += 1
        return chat(base, key, run_name, messages, max_tokens=max_tokens, label=label, n=n, m=total)

    rows.append(one(f"{catalog_id}/short", [{"role": "user", "content": "Reply with exactly: OK"}], 16))
    warm = [
        {"role": "system", "content": "Stable cache prefix for vast cycle."},
        {"role": "user", "content": "Reply with exactly: PONG"},
    ]
    rows.append(one(f"{catalog_id}/cache-cold", warm, 16))
    rows.append(one(f"{catalog_id}/cache-warm", warm, 16))
    rows.append(
        one(
            f"{catalog_id}/long-2k",
            [{"role": "user", "content": approx_token_filler(2000) + "\n\nReply with exactly: LONG_OK"}],
            16,
        )
    )
    rows.append(
        one(
            f"{catalog_id}/long-8k",
            [{"role": "user", "content": approx_token_filler(8000) + "\n\nReply with exactly: LONG8_OK"}],
            16,
        )
    )
    if OCR_MD.is_file():
        text = OCR_MD.read_text(encoding="utf-8", errors="replace")[:4000]
        row = one(
            f"{catalog_id}/ocr-md",
            [{"role": "user", "content": f"Document:\n{text}\n\nWhat city? One short sentence."}],
            64,
        )
        row["accuracy_city"] = "Ho Chi Minh" in (row.get("content_preview") or "")
        rows.append(row)
    if vision and VISION_IMG.is_file():
        b64 = base64.b64encode(VISION_IMG.read_bytes()).decode()
        mime = "image/jpeg" if VISION_IMG.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        rows.append(
            one(
                f"{catalog_id}/vision",
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Main object in one short sentence."},
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        ],
                    }
                ],
                64,
            )
        )
    code = one(
        f"{catalog_id}/coding",
        [{"role": "user", "content": "Reply with ONLY this exact line:\nreturn a + b"}],
        32,
    )
    code["accuracy_coding"] = "return a + b" in (code.get("content_preview") or "")
    rows.append(code)

    n += 1
    print(f"running test case {n}/{total}: {catalog_id}/concurrency-2", flush=True)

    def conc(i: int) -> dict:
        return chat(
            base,
            key,
            run_name,
            [{"role": "user", "content": f"Reply with exactly: C{i}"}],
            max_tokens=8,
            label=f"{catalog_id}/concurrency-{i}",
            n=n,
            m=total,
        )

    conc_rows = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        for fut in as_completed([pool.submit(conc, i) for i in (1, 2)]):
            conc_rows.append(fut.result())
    rows.append(
        {
            "label": f"{catalog_id}/concurrency-2",
            "model": run_name,
            "ok": all(r.get("ok") for r in conc_rows),
            "walls": [r.get("wall_s") for r in conc_rows],
            "gpu": gpu_stats(),
            "results": conc_rows,
        }
    )
    return rows, n


def disk_free_gb() -> float | None:
    try:
        out = remote("df -B1 / | awk 'NR==2{print $4}'", timeout=30).strip()
        return round(int(out) / (1024**3), 2)
    except Exception:  # noqa: BLE001
        return None


def ollama_size_gb(tag: str) -> float | None:
    """Parse `ollama list` SIZE column for tag (e.g. 3.4 GB)."""
    try:
        out = remote("ollama list", timeout=60)
        for line in out.splitlines()[1:]:
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            if name == tag or name.startswith(tag.split(":")[0] + ":"):
                # SIZE is usually 3rd token like "3.4" "GB" or combined
                for i, p in enumerate(parts):
                    if p.upper() in {"GB", "MB"} and i > 0:
                        try:
                            val = float(parts[i - 1])
                        except ValueError:
                            continue
                        return round(val / 1024 if p.upper() == "MB" else val, 2)
                # fallback: NAME ID SIZE UNIT
                if len(parts) >= 3:
                    try:
                        return float(parts[2])
                    except ValueError:
                        pass
        return None
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    base = os.environ.get("VAST_TEST_BASE_URL", "").rstrip("/")
    key = os.environ.get("VAST_API_KEY") or os.environ.get("OPEN_BUTTON_TOKEN") or ""
    if not base:
        fail("set VAST_TEST_BASE_URL (e.g. http://127.0.0.1:11434/v1)")

    specs = json.loads(CATALOG.read_text())["models"]
    filt = os.environ.get("VAST_CYCLE_MODELS", "").strip()
    if filt:
        want = {x.strip() for x in filt.split(",") if x.strip()}
        specs = [m for m in specs if m["id"] in want or m.get("alias") in want]

    # ~9 cases/model (vision optional)
    per = 9
    total = len(specs) * per
    n = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("")
    rows: list[dict] = []

    def append(row: dict) -> None:
        rows.append(row)
        with OUT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    cleanup_all()
    idle_gpu = gpu_stats()

    for i, spec in enumerate(specs):
        mid = spec["id"]
        tag = OLLAMA_MAP.get(mid) or spec.get("ollama_model")
        if not tag:
            append({"label": f"{mid}/skip", "ok": False, "error": "no ollama map"})
            continue
        print(f"\n######## [{i+1}/{len(specs)}] deploy {mid} -> {tag} ########", flush=True)
        try:
            free_before = disk_free_gb()
            pull(tag)
            free_after = disk_free_gb()
            disk_pull_gb = (
                round(free_before - free_after, 2)
                if free_before is not None and free_after is not None
                else ollama_size_gb(tag)
            )
            run_name = tag
            if mid == "Qwen/Qwen3.8-27B":
                # prefer already-ctx tag name in map if present
                if tag.endswith("-ctx64k"):
                    run_name = tag
                else:
                    run_name = ensure_ctx64k(tag, "qwen3.8:27b-ctx64k", 65536)
            print(f"=== warm {run_name} ===", flush=True)
            remote(
                f"curl -sS -m 600 http://127.0.0.1:11434/api/generate "
                f"-d '{{\"model\":\"{run_name}\",\"prompt\":\"ping\",\"stream\":false,\"options\":{{\"num_predict\":4}}}}' >/tmp/warm.json; "
                f"tail -c 180 /tmp/warm.json; echo; "
                f"nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader",
                timeout=700,
            )
            resident = gpu_stats()
            overhead_mib = None
            if (
                isinstance(idle_gpu.get("vram_used_mib"), int)
                and isinstance(resident.get("vram_used_mib"), int)
            ):
                overhead_mib = resident["vram_used_mib"] - idle_gpu["vram_used_mib"]
            suite, n = run_model_suite(
                base, key, mid, run_name, bool(spec.get("vision")), n, total
            )
            cold = next((r for r in suite if r.get("label", "").endswith("/cache-cold")), None)
            warm = next((r for r in suite if r.get("label", "").endswith("/cache-warm")), None)
            append(
                {
                    "label": f"{mid}/overhead-kv-summary",
                    "model": run_name,
                    "ok": True,
                    "catalog_id": mid,
                    "ollama_tag": run_name,
                    "disk_pull_gb": disk_pull_gb,
                    "ollama_list_size_gb": ollama_size_gb(run_name) or ollama_size_gb(tag),
                    "vram_idle_mib": idle_gpu.get("vram_used_mib"),
                    "vram_resident_mib": resident.get("vram_used_mib"),
                    "vram_runtime_overhead_mib": overhead_mib,
                    "vram_total_mib": resident.get("vram_total_mib"),
                    "kv_cache_cold": {
                        "wall_s": (cold or {}).get("wall_s"),
                        "cached_tokens": (cold or {}).get("cached_tokens"),
                        "cache_hit_percent": (cold or {}).get("cache_hit_percent"),
                        "prompt_tokens": (cold or {}).get("prompt_tokens"),
                    },
                    "kv_cache_warm": {
                        "wall_s": (warm or {}).get("wall_s"),
                        "cached_tokens": (warm or {}).get("cached_tokens"),
                        "cache_hit_percent": (warm or {}).get("cache_hit_percent"),
                        "prompt_tokens": (warm or {}).get("prompt_tokens"),
                    },
                }
            )
            for row in suite:
                append(row)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR on {mid}: {exc}", flush=True)
            append({"label": f"{mid}/deploy", "model": mid, "ok": False, "error": str(exc)[:600]})
        finally:
            print(f"=== cleanup after {mid} ===", flush=True)
            try:
                cleanup_all()
                idle_gpu = gpu_stats()
            except Exception as exc:  # noqa: BLE001
                print(f"cleanup warn: {exc}", flush=True)

    ok = sum(1 for r in rows if r.get("ok"))
    print(json.dumps({"wrote": str(OUT), "rows": len(rows), "ok": ok, "models": len(specs)}, indent=2))


if __name__ == "__main__":
    main()
