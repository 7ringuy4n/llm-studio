# Hardware requirements (llm-studio)

Sizing for the **VPN inference API** on a CPU-only Ubuntu host. Companion to
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

## Recommended minimums

| Setup | Min | Comfortable |
|-------|-----|-------------|
| API only (local Traefik) | 2 vCPU · 8 GiB · 40 GB | 4 vCPU · 16 GiB · 80 GB |
| API + OpenObserve + OTel | 4 vCPU · 16 GiB · 100 GB | same (leave 1 core free) |
| + large GGUF (8B) resident | 4 vCPU · 16 GiB · 120 GB+ | prefer unload idle |

Stop the API before heavy training runs under `/opt/data/llm-studio/training`.
