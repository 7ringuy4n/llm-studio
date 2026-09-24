# Agent Operations Rules — llm-studio

**Audience:** Cursor agents and human operators working on this repository.
**Source of truth:** This file under [`rule/`](./AGENT_RULES.md).
**Lab methodology:** [`../test/README.md`](../test/README.md)
**Git workflow:** [`GIT.md`](./GIT.md)
**Change history:** [`../docs/CHANGELOG.md`](../docs/CHANGELOG.md)
**Root-cause history (by date):** [`../history/README.md`](../history/README.md)

> These rules govern agent behavior. Do not hardcode them into application
> runtime messages, prompts, or business logic. Never store secrets in
> agent-memory, reports, or git.

------------------------------------------------------------------------

## 1. Mission

Maintain llm-studio as a **private production-adjacent inference API**
(VPN Traefik → API → optional OpenObserve) for long-term correctness and
ops safety.

Priorities:

1. Correctness
2. Security and data protection (API key, isolation from Hermes)
3. Architectural integrity (one resident model, catalog as SoT)
4. Root-cause resolution (fix in repo setup/source, not VPS-only sed)
5. Reliability and fault tolerance
6. Performance (CPU headroom for OO / OTel / Traefik / Docker / kernel)
7. Maintainability
8. Memory efficiency
9. Operational simplicity

Never sacrifice correctness or isolation merely to make a test pass.

------------------------------------------------------------------------

## 2. Hard gates

- Never weaken, delete, bypass, or manipulate tests to obtain a pass.
- Never leave a lab-only hotpatch as the permanent fix.
- Never fix a production bug only on the VPS — land it in compose,
  `.env.example`, scripts, or API code.
- Never attach Hermes networks/volumes or mount the Docker socket.
- Never commit `LLM_STUDIO_API_KEY`, OpenObserve passwords, or SSH
  credentials. Never print Bearer tokens in reports.
- Always ask the user before creating merge requests or pushing.
- Before work: read `docs/CHANGELOG.md`, `docs/HISTORY.md`, and
  dated folders under `history/`.
- When running tests, print progress as `running test case N/M`. If a
  failure is a real core bug, fix the core and re-run.
- **Client Stop / abort:** generation must be cancellable on the VPS. Prefer
  HTTP disconnect (DSH Stop / aborted fetch). If the socket stays open, call
  `POST /v1/generation/cancel` with the same `X-Correlation-ID` (or
  request/session id). Never leave orphaned long generations after Stop.
- **All living LLM models:** live / harness / browser lab gates must cover
  every model listed under the DSH `homelab` provider (and matching
  `configs/models.json` living entries), not only the default 0.8B.
- **Prompts:** each covered model gets **short** and **~10k-token long**
  prompts (tool-trace style context); prefer real-world ops wording. Include
  **continuous** multi-turn sessions and **concurrency** probes where the API
  lab applies.
- **Vision:** for vision-capable models, run **simple** and **complicated**
  image cases (objects + nature wallpaper) via
  `test/scripts/vision_contract.py`.
- **OCR / office docs:** run `test/scripts/ocr_docs_contract.py` against real
  files under `Documents/Work/test docs/OCR` (override with
  `LLM_STUDIO_OCR_ROOT`): **pdf, docx, md, xlsx, csv, pptx**, plus jpg/png
  vision reads. Assert grounded answers from extracted text / images.
- **DSH modes:** harness / browser labs run **`minimal`**, **`minimal + web`**,
  and **`standard`** presets (`agent-presets.default` / Minimal + Web), via
  `test/scripts/dsh_harness_contract.py` and BrowserSkill when authorized.
- **DSH auto-compact / continue (web):** continuous **coding-agent** flood in
  **Standard mode** growing toward max `contextWindow` until compact UI,
  overflow, or continue-OK — `rule/DSH_COMPACT_FLOOD.md` +
  `test/scripts/dsh_web_compact_flood.sh`. After compact, send continue turns.
  API continuous growth: `test/scripts/coding_agent_max_ctx_compact_lab.py`.
  Minimal mode must not be used as the compact SoT (compaction absent).
- **Reasoning × cache:** live labs must cover **both cache hit and no-cache**
  paths when switching `reasoning_effort` (same shared prefix, change effort).
  Use `test/scripts/reasoning_cache_contract.py` (warm same-effort → expect
  cache%; switch effort → expect miss / reduced hit). Browser / DSH UI labs
  should also record Cache hit % when changing Effort.
- Prefer `test/scripts/all_models_prompt_contract.py`,
  `test/scripts/realworld_api_contract.py`,
  `test/scripts/dsh_harness_contract.py`,
  `test/scripts/reasoning_cache_contract.py`,
  `test/scripts/ocr_docs_contract.py`,
  `test/scripts/vision_contract.py`, and
  `test/scripts/dsh_web_compact_flood.sh` (bsk Standard compact).

------------------------------------------------------------------------

## 3. CPU / performance defaults

On the 4-vCPU VPS, default **`LLM_STUDIO_API_CPUS=3.0`** and
**`LLM_STUDIO_CPU_THREADS=3`**. Leave ≥1 host vCPU for OpenObserve, OTel,
Traefik, Docker, and the kernel. Change only after a measured matrix
(`docs/16-cpu-performance.md`, `docs/perf-results/`).

------------------------------------------------------------------------

## 4. History entries

Dated folders under `history/YYYY-MM-DD/` must include Technical detail
(env keys bad→fixed, functions, API fields).

------------------------------------------------------------------------

## 5. Verification

- Offline: `./test/run.sh` (or `make test`) / `make test-all`
- Live (VPN): **all living models**, short+long
  (`test/scripts/all_models_prompt_contract.py`)
- Live (VPN): reasoning-effort **cache hit + miss**
  (`test/scripts/reasoning_cache_contract.py`)
- DSH harness: `test/scripts/dsh_harness_contract.py` (headless, all models)
- DSH web compact/continue: `test/scripts/dsh_web_compact_flood.sh`
  (**Standard** coding-agent max-ctx flood; `rule/DSH_COMPACT_FLOOD.md`)
- API coding-agent max-ctx: `test/scripts/coding_agent_max_ctx_compact_lab.py`
- Optional: `test/scripts/web_search_contract.py`
- Browser checks (OpenObserve / DSH) use the operator browser skill when
  authorized; exercise **all** living models in the UI when that lab is
  in scope. Never paste secrets into the page or chat logs.
