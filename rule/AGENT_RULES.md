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
  `history/task_on_progress.md`.
- When running tests, print progress as `running test case N/M`. If a
  failure is a real core bug, fix the core and re-run.
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
- **DSH modes:** harness labs run both **`minimal`** and **`standard`** presets
  (`agent-presets.default`), via `test/scripts/dsh_harness_contract.py`.
- Prefer `test/scripts/all_models_prompt_contract.py`,
  `test/scripts/realworld_api_contract.py`,
  `test/scripts/dsh_harness_contract.py`, and
  `test/scripts/vision_contract.py`.

------------------------------------------------------------------------

## 3. CPU / performance defaults

On the 4-vCPU VPS, default **`LLM_STUDIO_API_CPUS=3.0`** and
**`LLM_STUDIO_CPU_THREADS=3`**. Leave ≥1 host vCPU for OpenObserve, OTel,
Traefik, Docker, and the kernel. Change only after a measured matrix
(`docs/16-cpu-performance.md`, `docs/perf-results/`).

------------------------------------------------------------------------

## 4. History entries

Dated folders under `history/YYYY-MM-DD/` must include Technical detail
(env keys bad→fixed, functions, API fields). Update
`history/task_on_progress.md` while working.

------------------------------------------------------------------------

## 5. Verification

- Offline: `./test/run.sh` (or `make test`) / `make test-all`
- Live (VPN): **all living models**, short+long
  (`test/scripts/all_models_prompt_contract.py`)
- DSH harness: `test/scripts/dsh_harness_contract.py` (headless, all models)
- Optional: `test/scripts/web_search_contract.py`
- Browser checks (OpenObserve / DSH) use the operator browser skill when
  authorized; exercise **all** living models in the UI when that lab is
  in scope. Never paste secrets into the page or chat logs.
