#!/usr/bin/env python3
"""Per-model context resolution for labs (no shared/common ctx suite).

Each catalog entry owns its test max via, in order:
  ollama_num_ctx → test_context_tokens → context_tokens

Never clamp all models to one global window (e.g. 4k/8k/32k).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # llm-studio/
CATALOG = ROOT / "configs" / "models.json"

OLLAMA_MAP = {
    "Qwen/Qwen3.5-0.8B": "qwen3.5:0.8b",
    "Qwen/Qwen3.5-2B": "qwen3.5:2b",
    "Qwen/Qwen3.5-4B": "qwen3.5:4b",
    "Qwen/Qwen3.5-9B": "qwen3.5:9b-ctx128k",
    "Qwen/Qwen3-1.7B": "qwen3:1.7b",
    "Qwen/Qwen3-8B": "qwen3:8b",
    "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B": "deepseek-r1:7b",
    "meta-llama/Llama-3.1-8B-Instruct": "llama3.1:8b",
    "Qwen/Qwen3.8-27B": "qwen3.8:27b-ctx64k",
}


def load_models() -> list[dict]:
    return json.loads(CATALOG.read_text())["models"]


def find_model(key: str) -> dict:
    for m in load_models():
        if key in (m["id"], m.get("alias"), m.get("ollama_model"), OLLAMA_MAP.get(m["id"])):
            return m
    raise KeyError(f"model not in catalog: {key}")


def test_context_tokens(spec: dict) -> int:
    for field in ("ollama_num_ctx", "test_context_tokens", "context_tokens"):
        v = spec.get(field)
        if v is not None:
            return int(v)
    return 32768


def ollama_tag(spec: dict) -> str:
    return (
        spec.get("ollama_model")
        or OLLAMA_MAP.get(spec["id"])
        or spec["id"]
    )


def flood_chunk_reps(ctx: int) -> int:
    """Per-model filler size for UI floods (bsk fill ≤~3500 chars)."""
    # ~9 chars per "ops-note "; keep under ~3200 chars of filler
    target_chars = min(3200, max(400, ctx // 40))
    return max(40, target_chars // 9)


def flood_max_turns(ctx: int) -> int:
    """More turns for larger windows; still bounded for lab wall-clock."""
    if ctx <= 8192:
        return 40
    if ctx <= 32768:
        return 80
    if ctx <= 65536:
        return 120
    return 160


if __name__ == "__main__":
    import sys

    key = sys.argv[1] if len(sys.argv) > 1 else ""
    if not key:
        for m in load_models():
            print(f"{m['id']}\t{test_context_tokens(m)}\t{ollama_tag(m)}")
        raise SystemExit(0)
    m = find_model(key)
    ctx = test_context_tokens(m)
    print(
        json.dumps(
            {
                "id": m["id"],
                "alias": m.get("alias"),
                "ollama_tag": ollama_tag(m),
                "test_context_tokens": ctx,
                "catalog_context_tokens": m.get("context_tokens"),
                "chunk_reps": flood_chunk_reps(ctx),
                "max_turns": flood_max_turns(ctx),
            }
        )
    )
