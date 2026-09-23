# 2026-09-21 — Multi-model runtime + observability

## Summary

Catalog-driven multi-model API (one resident at a time), idle unload, GGUF
LlamaRAMCache, tool-calling contract, OpenObserve/OTel request tracing
(`llm_studio_requests`). First/last-token headers, cache-hit percent, session
affinity.

## Technical detail

- Catalog: `configs/models.json`
- Idle unload: `MODEL_IDLE_UNLOAD_SECONDS` (default 3600)
- Trace stream: `llm_studio_requests` via OTel collector → OpenObserve
- Affinity headers: `X-Session-ID` / `x-session-affinity`
