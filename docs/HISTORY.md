# Project history

Narrative companion to `CHANGELOG.md`. Prefer CHANGELOG for bullet facts;
this file records why decisions landed and how the VPS is meant to be used.

## 2026-09-23 — Why DSH shows 0% cache on Qwen3.5-0.8B

OpenObserve `cache_hit_percent` measures **cross-request prompt prefix reuse**,
not “same chat” alone. That reuse is implemented for **GGUF** via
`LlamaRAMCache`. Multimodal HF models (`Qwen3.5-0.8B` / `2B`) only keep KV for
the current `generate()` call, so every turn re-prefills; first-token time
grows with history. Session
`session-96445663-45dd-4694-bedd-733b78f67079` had correct session affinity and
nine completed turns at **0%** cache — expected for that backend. Switch to a
GGUF living model (e.g. `Qwen/Qwen3-8B`) to see non-zero `cached_input_tokens`.

## 2026-09-23 — Stop must cancel VPS generation

DeepSeek Harness **Stop** (and aborted HTTP clients) previously only stopped
the UI stream while the single resident model on the VPS kept generating until
`max_tokens` / EOS. That wasted CPU and blocked the concurrency slot.

Fix is **cooperative cancel**: disconnect watcher + optional
`POST /v1/generation/cancel` set a `CancelToken`; HF `StoppingCriteria` and
GGUF logits processors abort the worker loop. Timeouts now request the same
cancel instead of only orphaning a thread behind a held slot.

Clients should keep sending a stable `X-Correlation-ID` so an explicit cancel
can target the same in-flight job if the socket is not torn down.

## 2026-09-23 — Real-world readiness: tokens, docs, CPU, tools, affinity

LLM Studio is treated as a **private production-adjacent inference API** for
DSH (and similar clients) on a 4-vCPU / 16 GiB CPU VPS over VPN
(`10.8.0.1:18080`), not only a training lab.

**Completion limits.** Catalog `max_new_tokens` moved from a flat 2048 to each
model’s practical ceiling (32768 for living Qwen3.5 / GGUF models; 16384 for
Qwen3-1.7B). The process-wide `MODEL_MAX_NEW_TOKENS` default matches 32768 so
clients can request long answers, tool traces, and thinking without a 400.
Generation still reserves prompt room inside the active context window (GGUF
also capped by `MODEL_GGUF_CONTEXT_TOKENS`, default 32768).

**CPU.** Explicit llama.cpp `n_batch`/`n_ubatch`/mmap, BLAS thread pinning, and
a measurable `LLM_STUDIO_API_CPUS` switch. A full reasoning-effort matrix vs
`model-statistic 2.docx` showed **3 API vCPUs** remain the default: 4 cores
improved some cold first-token numbers but raised mean wall time (~+26%) when
OS/OpenObserve had no spare core. Prefix RAM cache remains the largest
first-token win on turn 2+.

**Tools / DSH.** Web search and fetch are executed by DSH
(`dsh-web-search-free` → Tavily), not by llm-studio. Stock Minimal has no web
tools; use Standard or Minimal + Web. Session affinity headers
(`X-Session-ID` / `x-session-affinity`) keep OpenObserve `session_id` stable
across model switches; `model_loaded` / `model_unloaded` record residency.

**Docs/tests.** Hermes-style `CHANGELOG` / `HISTORY` / `test/` (merged former
`tests/` into `test/scripts/`) / `history/` / `rule/` plus perf artifacts under
`docs/perf-results/`. Live labs require **short and long** prompts
(`test/scripts/prompt_length_contract.py`).

## 2026-09-21 — Multi-model + observability

The service stopped being single-checkpoint: allowed models are listed in
`configs/models.json`, only one resident at a time, idle unload after an hour,
GGUF LlamaRAMCache for prompt prefix reuse. OpenObserve (optional profile)
receives structured request/response traces with token timing and cache hit
percent. Tool-calling is an OpenAI-compatible contract; the harness owns
network search.

## 2026-09-20 — Secure studio from zero

Built for coexistence with Hermes: dedicated Compose project and network,
Traefik without Docker socket, loopback/VPN bind only, Bearer key, non-root
read-only API container. Default model Qwen3.5-0.8B multimodal with a written
CPU training curriculum (`docs/01`–`12`) that does not modify the API image.
Backup/restore and environment inspection scripts are first-class so VPS
rebuilds stay reproducible.

## Real-world usage notes

- Prefer **Qwen3.5-2B** for tool calling on this VPS; 0.8B is flaky; 8B/R1/Llama
  often skip tools unless forced.
- Keep **one concurrent generation**; queue instead of raising concurrency on
  CPU.
- Leave API at **3 CPUs**; use `./scripts/set_api_cpus.sh 4` only for measured
  experiments.
- Point DSH `homelab` at `http://10.8.0.1:18080/v1` with the Bearer key in
  credentials refs — never commit keys.
- Request `max_tokens` up to the model’s catalog limit; expect slow long
  completions on CPU (minutes, not seconds).
