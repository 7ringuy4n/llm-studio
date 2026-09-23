# Hardware requirements (llm-studio)

Sizing for the **VPN inference API** on a CPU-only Ubuntu host, plus **GPU
offload** for large catalog entries (`deployment: vast-ollama`). Companion to
Hermes-style `docs/HARDWARE.md`, scoped to this stack only.

## Tested lab (successful multi-model + OpenObserve)

| Item | Value |
|------|-------|
| Date | 2026-09-23 |
| OS | Ubuntu 24.04 (VPS) |
| CPU | **4 vCPU** |
| RAM | **16 GiB** |
| Disk | SSD with `/opt/data/llm-studio` for HF/GGUF caches |
| API CPU quota | **`LLM_STUDIO_API_CPUS=3.0`** / **`LLM_STUDIO_CPU_THREADS=3`** |
| Headroom | ≥1 vCPU for OpenObserve, OTel, Traefik, Docker, kernel |
| API | Traefik → `10.8.0.1:18080` |
| OpenObserve | host port **15080** (observability profile) |

## Why not 4 API vCPUs

A full reasoning-effort matrix showed **4.0** API CPUs can improve some cold
first-token numbers but raised **mean wall time** (~+26%) when observability
and the OS had no spare core. Keep **3.0** as the always-on default. Details:
[16-cpu-performance.md](./16-cpu-performance.md), `docs/perf-results/`.

## Recommended minimums (CPU VPS)

| Setup | Min | Comfortable |
|-------|-----|-------------|
| API only (local Traefik) | 2 vCPU · 8 GiB · 40 GB | 4 vCPU · 16 GiB · 80 GB |
| API + OpenObserve + OTel | 4 vCPU · 16 GiB · 100 GB | same (leave 1 core free) |
| + large GGUF (8B) resident | 4 vCPU · 16 GiB · 120 GB+ | prefer unload idle |

## Per-model hardware — CPU VPS vs Vast

| Model | Backend | CPU VPS min → comfort | Vast GPU VRAM (measured) | HDD weights (Ollama pull, measured) | Coding fit | Cache / notes |
|-------|---------|----------------------|--------------------------|--------------------------------------|------------|---------------|
| Qwen3.5-0.8B | HF / Ollama | 4c / 16 GiB → same | **~2.7 GB** | **1.0 GB** | **No** — chat/vision only | Ollama cache-warm ~86%; HF CPU cache% 0 |
| Qwen3.5-2B | HF / Ollama | 4c / 16 GiB → same | **~4.5 GB** | **2.7 GB** | **No** — chat/vision only | Ollama cache-warm ~86% |
| Qwen3-1.7B | HF / Ollama | 4c / 12 GiB → 16 GiB | **~6.3 GB** | **1.4 GB** | **No** — text smoke only | Enable on CPU `MODEL_ALLOWED_MODELS`; Vast OK |
| Qwen3-8B Q4 | GGUF / Ollama | 4c / 16 GiB → 16+ GiB | **~11.3 GB** | **5.2 GB** | **Conditional** — snippets if thinking off + higher `max_tokens`; not primary coding agent | Long-2k ~9s GPU vs ~141s CPU |
| DeepSeek-R1 7B Q4 | GGUF / Ollama | 4c / 16 GiB → 16+ GiB | **~9.0 GB** | **4.7 GB** | **Conditional** — hard reasoning coding with large token budget; weak on exact short replies | Long-2k ~7s GPU vs ~130s CPU |
| Llama 3.1 8B Q4 | GGUF / Ollama | 4c / 16 GiB → 16+ GiB | **~13.6 GB** | **4.9 GB** | **Yes** — best ≤8B for exact coding replies (Vast lab **PASS**) | OCR+coding PASS on Vast |
| **Qwen3.8 27B Q4** | **Vast Ollama** | **Not on 16 GiB CPU** | **~20–22 GB** @ 64k | **~17 GB** | **Yes (primary)** — Vast coding-agent pick; give enough `max_tokens` | Need container **≥40 GB** HDD |

| Lane | Min HDD | Comfortable HDD |
|------|---------|-----------------|
| CPU VPS (catalog ≤8B + OO) | 80 GB | **100–120 GB** |
| Vast (one resident + cleanup) | 20 GB (≤8B) | **≥40 GB** for 27B on 32 GB overlays |

Do **not** add `Qwen/Qwen3.8-27B` to `MODEL_ALLOWED_MODELS` on the CPU VPS
(`deployment: vast-ollama`). Point DSH `vast` at a **localhost SSH tunnel** to
Ollama (never commit the public mapped host:port).

### When to rent Vast (any catalog model)

| Need | Prefer |
|------|--------|
| Daily ≤8B chat + tools on budget | CPU VPS (3 API cores) |
| Vision/OCR or long-prompt latency for ≤8B | Vast 12–16 GB |
| **27B** or 64k context | Vast **32 GB VRAM**, `qwen3.8:27b-ctx64k` |
| Switch between large pulls | Free disk between models (≥40 GB container) |

### Vast / GPU checklist

- Template: Ollama (or llama.cpp)
- Match VRAM class to the table above (8–12 / 16 / 24 / 32 GB)
- Container disk **≥40 GB** when pulling ≥17 GB weights (32 GB fills fast)
- DSH `contextWindow` must match Ollama `num_ctx` (27B: use `qwen3.8:27b-ctx64k`)
- One resident model; unload before the next large pull

Full dual-lane case tables: [perf-results/model-statistic-report.md](./perf-results/model-statistic-report.md) §9 (CPU) + §9b (Vast GPU).


Stop the API before heavy training runs under `/opt/data/llm-studio/training`.
