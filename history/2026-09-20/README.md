# 2026-09-20 — Secure VPN inference API

## Summary

Initialized llm-studio: isolated Compose (API + mode-specific Traefik), Bearer
API key, read-only rootfs, capability drop. Qwen3.5 multimodal default path,
training handbook under `docs/01`–`12`.

## Technical detail

- No Hermes volumes/networks; no Docker socket mount
- Traefik profiles: `local` / `internet`
- Data root: `/opt/data/llm-studio` (VPS)
