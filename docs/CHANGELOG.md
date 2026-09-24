## 2026-09-24 — OpenCode + DSH catalog auto-compact proofs

- OpenCode auto-compact flood (`test/scripts/opencode_compact_flood.sh`) with
  `limit.input` so `compaction.reserved` applies; token-drop detector.
- Catalog cycle driver `test/scripts/catalog_compact_cycle.py` (per-model pull,
  Modelfile `num_ctx`, DSH Standard + OpenCode, cleanup between models).
- Small-ctx (≤40k) **PASS** both agents: 0.8B, 2B, 1.7B, 4B, 8B. Prior: OpenCode
  9B@128k + 27B@64k; DSH 9B@128k.
- Report: DSH vs OpenCode cost/quota verdict (DSH earlier trigger on 9B).
- Artifacts under `docs/perf-results/*compact*` / `catalog-compact-cycle.jsonl`.

## 2026-09-24 — Drop history/task_on_progress; coding-agent max-ctx compact

- Removed `history/task_on_progress.md`; handoff lives in dated `history/` +
  agent-memory only.
- Continuous **coding-agent** growth to near-max context: API lab
  `coding_agent_max_ctx_compact_lab.py`; DSH Standard flood grows coding turns
  and **continues after compact** (`DSH_COMPACT_CONTINUE_AFTER`).

## 2026-09-24 — Catalog +4B/+9B; Vast cycle overhead & KV

- Added `Qwen/Qwen3.5-4B` and `Qwen/Qwen3.5-9B` (multimodal) to `configs/models.json`.
- `vast_catalog_cycle_lab.py`: OLLAMA_MAP for `qwen3.5:4b` / `qwen3.5:9b`; default SSH
  Vast host from lab-temp; per-model **runtime overhead** (idle→resident VRAM) +
  **KV cache cold/warm** summary rows in `vast-all-models-cycle.jsonl`.
- Report/HARDWARE updates follow measured cycle results.

## 2026-09-23 — Hardware: CPU VPS + Vast per model

- `docs/HARDWARE.md` and `model-statistic-report.md` §8 now list **both** CPU VPS
  and Vast GPU min/comfortable sizing for every catalog model (not only 27B).
- 27B remains Vast-only; ≤8B can stay on CPU or move to 12–16 GB GPU for latency.

## 2026-09-23 — Qwen3.8 27B on Vast + catalog deployment field

- `configs/models.json`: `Qwen/Qwen3.8-27B` with `deployment: vast-ollama` /
  `ollama_model: qwen3.8:27b-ctx64k` (not loadable via CPU
  `MODEL_ALLOWED_MODELS`).
- Lab harness `test/scripts/vast_qwen38_27b_lab.py`; results in
  `docs/perf-results/vast-qwen38-27b-lab.jsonl` (short/cache/long/OCR/vision/
  concurrency/tools — **9/9 PASS** on 32 GB VRAM).
- Hardware + statistic report updated for per-model GPU vs CPU guidance.

## 2026-09-23 — Cache hit only on GGUF (HF multimodal always 0%)

- Investigated DSH session `session-96445663-…`: multi-turn same session, but
  `cache_hit_percent` stayed `0.0` on every turn.
- Root cause: resident model was HF **multimodal** `Qwen/Qwen3.5-0.8B`. Cross-
  request prompt prefix cache (`LlamaRAMCache` / `MODEL_KV_CACHE_BYTES`) applies
  only to `backend=gguf`. HF `use_cache=True` is **within one generation** only.
- Session affinity was fine (stable `X-Session-ID`). Live probe: 0.8B turn2
  **0%**; `Qwen/Qwen3-8B` turn2 **~26%** with `X-KV-Cache: prompt-and-generation`.
- History: `history/2026-09-23/cache-miss-session-96445663.md`.

## 2026-09-23 — Generation cancel on Stop / disconnect

- Cooperative cancel for in-flight `/v1/chat/completions`: client disconnect
  (DeepSeek Harness Stop / aborted fetch) flips a per-request cancel token;
  HF `StoppingCriteria` and GGUF logits callbacks stop the VPS worker instead
  of finishing the full generation.
- Explicit `POST /v1/generation/cancel` with `correlation_id` / `request_id` /
  `session_id` (or matching headers) for clients that keep the socket open.
- Request timeout also requests cancel (no longer only holds the concurrency
  slot until the orphaned thread exits).
- Offline unit: `test/scripts/cancellation_unit.py` (wired into `run_all.sh`).

## 2026-09-23 — ~10k-token long prompts + vision simple/complicated

- Long-prompt labs target **~10k tokens** of tool-trace style context
  (`test/scripts/prompt_builders.py`).
- Vision contract: simple panels/object + complicated nature wallpaper / desk
  scene for Qwen3.5 vision models (`make test-vision`, fixtures under
  `test/fixtures/vision/`).
- Updated `postman/`: folders for all-models short+~10k long, real-world
  continuous, vision simple/complicated; fixtures copied; env vars and README.

## 2026-09-23 — All-model API + DSH minimal/standard; real-world concurrency

- Agent rule: labs cover **all living models**, short+long **real-world**
  prompts, **continuous** multi-turn, **concurrency**, and DSH presets
  **minimal** + **standard**.
- Scripts: `all_models_prompt_contract.py` (`make test-models`),
  `realworld_api_contract.py` (`make test-realworld`),
  `dsh_harness_contract.py` (`make test-dsh`).
- Perf reference: `docs/perf-results/comparison.md` (keep **3.0 / 3 threads**).

## 2026-09-23 — history/rule layout; merge test folders; short+long prompts

- Merged former `tests/` into `test/scripts/`; gates are `test/run.sh` and
  `test/run_all.sh` (`make test`) with `running test case N/M` progress.
- Added `history/` (dated root-cause log + `task_on_progress.md`) and `rule/`
  (`AGENT_RULES`, `GIT`, `TEST_STRATEGY`, `SETUP.local`) fitted to llm-studio.
- Docs: `HARDWARE.md`, `SECURITY.md`; live `prompt_length_contract.py`
  (short + long prompts). CPU default remains **3.0 / 3 threads**.
- Fixed `tracing_unit.py` to force the test API key (container runs were
  getting 401 via `setdefault` against the live `LLM_STUDIO_API_KEY`).

## 2026-09-23 — Docs history/test index; per-model max tokens to catalog limits

- Added Hermes-style project docs: `docs/CHANGELOG.md`, `docs/HISTORY.md`,
  `test/README.md`, `test/REPORT.md` (plus `docs/perf-results/`).
- Raised completion ceilings for real-world use: catalog `max_new_tokens` is
  now **32768** for living multimodal/GGUF models (16384 for Qwen3-1.7B);
  global `MODEL_MAX_NEW_TOKENS` default **32768** (settings max 131072).
- DSH `dsh-config` / homelab `maxTokens` and `defaultMaxTokens` follow the
  catalog. Prompt room is still enforced as
  `context − max_new_tokens` at generation time.
- CPU performance work earlier the same day: GGUF `n_batch`/`mmap`,
  `LLM_STUDIO_API_CPUS`, 3 vs 4 vCPU matrix, keep **3** API cores; Tavily via
  `dsh-web-search-free`; session affinity + `model_loaded`/`model_unloaded`
  traces. See HISTORY for narrative.

## 2026-09-21 — Multi-model runtime and OpenObserve observability

- Merged multi-model catalog (Qwen3.5 0.8B/2B, Qwen3-8B GGUF, DeepSeek-R1 7B
  GGUF, Llama 3.1 8B GGUF), idle unload, KV RAM cache for GGUF, tool-calling
  contract, and OpenObserve/OTel request tracing (`llm_studio_requests`).
- Exposed first/last-token headers, cache-hit percent, and session/correlation
  IDs on `/v1/chat/completions`.

## 2026-09-20 — Secure VPN API studio; Qwen3.5 multimodal

- Initialized the `llm-studio` repository and shipped the isolated Compose
  stack (API + mode-specific Traefik, no Hermes attachment, Bearer API key,
  read-only rootfs, capability drop).
- Upgraded the default path to Qwen3.5 multimodal (`AutoModelForMultimodalLM`),
  262144-context catalog entries, embedded image data-URL validation, and the
  training handbook under `docs/01`–`12`.
- Postman collection/environment import fixes; local vs internet Traefik
  profiles; backup/restore scripts with SHA256 verification.

## 2026-09-20 — Repository bootstrap

- `chore: initialize llm-studio repository` — empty project scaffold before the
  VPN API feature branch.
