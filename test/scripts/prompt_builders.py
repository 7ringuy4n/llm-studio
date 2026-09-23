#!/usr/bin/env python3
"""Shared prompt builders for llm-studio labs (~10k-token long prompts)."""

from __future__ import annotations


def approx_token_filler(target_tokens: int = 10000, unit: str | None = None) -> str:
    """Build repetitive ops/tool-trace text approximating target_tokens (≈4 chars/token)."""
    unit = unit or (
        "Tool-trace context: web_search query='homelab traefik openobserve'; "
        "hit title='VPN API checklist' url='https://example.invalid/ops' "
        "snippet='Bind Traefik to 10.8.0.1:18080; leave one vCPU free for OO/OTel.' "
    )
    # Rough English BPE density ~4 characters per token.
    need_chars = max(target_tokens, 1) * 4
    reps = max(1, (need_chars + len(unit) - 1) // len(unit))
    return unit * reps


def long_realworld_prompt(question: str, *, target_tokens: int = 10000) -> str:
    return (
        "Ops / tool-call background (treat as retrieved context; do not invent tools):\n"
        + approx_token_filler(target_tokens)
        + "\n\nQuestion: "
        + question
    )


SHORT_REAL = (
    "I restarted llm-studio on the VPS this morning. "
    "Give me a 1-sentence checklist item to confirm the API is healthy over VPN."
)

LONG_REAL_QUESTION = (
    "In one short paragraph, explain why we keep LLM_STUDIO_API_CPUS=3.0 on a "
    "4-vCPU host when OpenObserve is running."
)
