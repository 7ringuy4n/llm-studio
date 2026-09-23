# 2026-09-23 — Real-world readiness + CPU matrix

## Summary

Raised completion ceilings to catalog limits; added Hermes-style docs/test
index; measured **3 vs 4** API vCPUs on the 4-vCPU VPS; kept **3** as default
so OpenObserve / OTel / Traefik / Docker / kernel retain headroom. Merged
`tests/` into `test/`; added `history/` and `rule/`.

## Technical detail

| Area | Bad / prior | Fixed |
|---|---|---|
| Catalog `max_new_tokens` | flat 2048 | 32768 (16384 for Qwen3-1.7B) |
| `MODEL_MAX_NEW_TOKENS` | lower default | 32768 (settings max 131072) |
| `LLM_STUDIO_API_CPUS` | try 4.0 | keep **3.0** (mean wall ~+26% on 4) |
| `LLM_STUDIO_CPU_THREADS` | match CPUs | **3** |
| Test layout | `test/` index + `tests/` scripts | single `test/` (`scripts/`, `run.sh`, `run_all.sh`) |

Perf artifacts: `docs/perf-results/`. Guide: `docs/16-cpu-performance.md`.

## Verification

- Offline: `./test/run_all.sh`
- Live: health + `/v1/models` + optional `web_search_contract.py` over VPN
