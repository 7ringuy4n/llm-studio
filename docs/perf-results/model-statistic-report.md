# LLM Studio model statistic report

**Date:** 2026-09-23  
**Host:** 4 vCPU · ~16 GiB RAM · VPN API `10.8.0.1:18080` · OpenObserve `:15080`  
**API CPU quota:** `LLM_STUDIO_API_CPUS=3.0` / `LLM_STUDIO_CPU_THREADS=3` (1 host core reserved for OO / OTel / Traefik / Docker / kernel)  
**Template:** structure follows `model-statistic 2.docx` (reasoning matrix + host notes + accuracy/cost)  
**Artifacts:** `docs/perf-results/comparison.md`, `test/reports/all-models-prompt-perf.json`

---

## 1. Reasoning-effort matrix (post-improvement, max_tokens 512 lab lineage)

Retest lineage: all cells HTTP 200. Tables below are the **post-improvement** 3-vCPU and 4-vCPU runs used for the keep-3 decision (full rows in `docs/perf-results/comparison.md`).

### 1.1 Three API vCPUs (recommended default)

| Model | Mode | Math / exact | Tokens in/out | Cache% | First token | Last token | Total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen3.5-0.8B | off | Yes / No | 54/42 | 0.0 | 0.358s | 6.166s | 6.296s |
| Qwen3.5-0.8B | low | Yes / No | 52/512 | 0.0 | 0.401s | 80.455s | 80.582s |
| Qwen3.5-0.8B | medium | Yes / No | 52/512 | 0.0 | 0.301s | 82.059s | 82.144s |
| Qwen3.5-0.8B | high | Yes / No | 52/512 | 0.0 | 0.328s | 66.408s | 66.499s |
| Qwen3.5-0.8B | xhigh | Yes / No | 52/512 | 0.0 | 0.347s | 89.641s | 89.73s |
| Qwen3.5-0.8B | max | Yes / No | 52/512 | 0.0 | 0.363s | 72.87s | 72.955s |
| Qwen3.5-2B | off | Yes / Yes | 54/18 | 0.0 | 1.218s | 5.104s | 13.736s |
| Qwen3.5-2B | low | Yes / Yes | 52/242 | 0.0 | 1.087s | 73.777s | 73.864s |
| Qwen3.5-2B | medium | Yes / Yes | 52/242 | 0.0 | 0.999s | 84.906s | 84.987s |
| Qwen3.5-2B | high | Yes / Yes | 52/242 | 0.0 | 0.559s | 63.776s | 63.897s |
| Qwen3.5-2B | xhigh | Yes / Yes | 52/242 | 0.0 | 0.62s | 75.029s | 75.159s |
| Qwen3.5-2B | max | Yes / Yes | 52/242 | 0.0 | 1.387s | 69.631s | 69.72s |
| Qwen3-8B | off | Yes / Yes | 51/8 | 0.0 | 6.892s | 9.792s | 25.204s |
| Qwen3-8B | low | Yes / Yes | 48/169 | 87.5 | 0.508s | 22.599s | 23.038s |
| Qwen3-8B | medium | Yes / Yes | 48/169 | 0.0 | 5.537s | 26.305s | 39.599s |
| Qwen3-8B | high | Yes / Yes | 48/237 | 100.0 | 0.23s | 28.573s | 29.093s |
| Qwen3-8B | xhigh | Yes / Yes | 48/237 | 100.0 | 0.37s | 33.977s | 34.713s |
| Qwen3-8B | max | Yes / Yes | 48/237 | 100.0 | 1.152s | 33.658s | 34.336s |
| DeepSeek-R1 7B | off | Yes / Yes | 46/233 | 0.0 | 2.608s | 30.297s | 41.14s |
| DeepSeek-R1 7B | low | Yes / Yes | 43/208 | 95.35 | 0.192s | 25.333s | 25.697s |
| DeepSeek-R1 7B | medium | Yes / Yes | 43/233 | 100.0 | 0.112s | 27.321s | 27.678s |
| DeepSeek-R1 7B | high | Yes / Yes | 43/233 | 100.0 | 0.149s | 26.147s | 26.52s |
| DeepSeek-R1 7B | xhigh | Yes / Yes | 43/233 | 100.0 | 0.134s | 27.041s | 27.389s |
| DeepSeek-R1 7B | max | Yes / Yes | 43/233 | 100.0 | 0.128s | 27.801s | 28.211s |
| Llama 3.1 8B | off | Yes / Yes | 73/3 | 0.0 | 4.315s | 4.719s | 16.997s |
| Llama 3.1 8B | low | Yes / Yes | 73/3 | 100.0 | 0.114s | 0.459s | 0.611s |
| Llama 3.1 8B | medium | Yes / Yes | 73/3 | 100.0 | 0.124s | 0.537s | 0.642s |
| Llama 3.1 8B | high | Yes / Yes | 73/3 | 100.0 | 0.114s | 0.449s | 0.628s |
| Llama 3.1 8B | xhigh | Yes / Yes | 73/3 | 100.0 | 0.113s | 0.446s | 0.559s |
| Llama 3.1 8B | max | Yes / Yes | 73/3 | 100.0 | 0.126s | 0.516s | 0.646s |

### 1.2 Four API vCPUs (experiment only)

See `docs/perf-results/comparison.md` § perf-cpus4. Mean total across 30 cells: **44.7s** vs **38.7s** on 3 vCPUs (**+15%**). Qwen3-8B high/xhigh/max regress sharply when the host has no spare core.

### 1.3 Three vs four — decision

| Metric | 3 vCPU | 4 vCPU |
| --- | --- | --- |
| Mean total wall (30 cells) | **38.7s** | 44.7s |
| Cold first-token | mixed | often better |
| Shared host headroom | **yes** (OO/OTel/Traefik/Docker/kernel) | none |
| **Recommendation** | **Keep 3.0 / 3 threads** | lab-only |

---

## 2. Short + long prompt lab (all living models, 2026-09-23)

Source: `test/reports/all-models-prompt-perf.json` (`make test-models`).
Thinking off. **Updated requirement:** long prompts target **~10k tokens** of tool-trace
style context (`prompt_builders.approx_token_filler`).

**~10k smoke (0.8B):** short `prompt_tokens=40` wall 11.1s; long
`prompt_tokens=13235` first-token 177s / wall 194s — **PASS**.

Earlier all-models availability pass (shorter long-prompt) remains below for
cross-model comparison:

| Model | Prompt | Tokens in/out | Cache% | First token | Last token | Total wall |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3.5-0.8B | short | 40/18 | 0.0 | 0.271s | 2.348s | 122.8s* |
| Qwen3.5-0.8B | long | 1600/26 | 0.0 | 6.330s | 9.436s | 9.6s |
| Qwen3.5-2B | short | 40/32 | 0.0 | 2.054s | 9.949s | 19.2s |
| Qwen3.5-2B | long | 1600/32 | 0.0 | 10.861s | 18.786s | 18.9s |
| Qwen3-8B | short | 39/5 | 0.0 | 2.862s | 3.533s | 18.4s |
| Qwen3-8B | long | 1600/5 | 1.12 | 84.268s | 84.992s | 86.4s |
| DeepSeek-R1 7B | short | 29/32 | 0.0 | 1.592s | 5.376s | 16.3s |
| DeepSeek-R1 7B | long | 1590/32 | 0.75 | 73.628s | 77.569s | 78.3s |
| Llama 3.1 8B | short | 58/1 | 0.0 | 2.900s | 3.019s | 15.7s |
| Llama 3.1 8B | long | 1618/1 | 2.47 | 84.210s | 84.382s | 86.1s |

\*First short on 0.8B includes cold multimodal load (~2 min).

**Result:** **10/10 PASS** (non-empty completions for every living model).

---

## 2b. Vision lab (simple + complicated)

Fixtures: `test/fixtures/vision/` (+ copies under `postman/fixtures/`).
Gate: `make test-vision` — **PASS 8/8** (2026-09-23).

| Model | Case | First token | Wall | Preview |
| --- | --- | --- | --- | --- |
| Qwen3.5-0.8B | simple panels | 0.92s | 112.9s* | 3 panels |
| Qwen3.5-0.8B | simple mug | 1.19s | 3.1s | coffee cup |
| Qwen3.5-0.8B | nature wallpaper | 4.97s | 12.6s | lake / trees / mountains |
| Qwen3.5-0.8B | desk scene | 3.62s | 7.4s | TV, tree, mouse |
| Qwen3.5-2B | simple panels | 4.44s | 18.0s | numeric “3.33…” |
| Qwen3.5-2B | simple mug | 3.06s | 16.5s | pen holder (misread) |
| Qwen3.5-2B | nature wallpaper | 11.69s | 28.1s | lake / trees / mountains |
| Qwen3.5-2B | desk scene | 8.97s | 13.8s | monitor, notes, tree… |

\*Includes model switch / vision warm-up.

---

## 3. Accuracy, cost, caching notes

| Topic | Finding |
| --- | --- |
| Accuracy | Prefer catalog models with measured exact-format wins (Qwen3-8B / Qwen3.5-2B with reasoning on for hard math). Llama reasoning_effort is effectively boolean; starred modes in the docx baseline were unsupported. |
| Cost | Local VPS inference = **$0 token API cost**; cost is **wall time + RAM residency** (one model loaded). Unload idle (1h) limits RAM waste. |
| Caching | GGUF prefix RAM cache is the largest **first-token** win on turn 2+ (see 3-vCPU table cache% rows). Multimodal path shows little cache on cold short/long probes. |
| First / last token | Expose `x-first-token-*` / `x-last-token-*` and `x-cache-hit-percent` for OpenObserve. Long prompts dominate TTFT via prompt eval. |
| Best practices | Match `CPU_THREADS` to `API_CPUS`; `n_batch`/`mmap` on; `mlock` off on 16 GiB; leave 1 host vCPU; use `off`/`low` when latency matters more than long thinking. |

---

## 4. Host / resource notes (from docx baseline + current ops)

| Item | Value |
| --- | --- |
| API cgroup | 3.0 CPUs |
| Failed / OOM requests (matrix) | 0 |
| Highest RAM demand | Qwen3-8B (~13 GiB class peaks in earlier telemetry) |
| Observability | OpenObserve + OTel on same host — do not pin API to 4.0 |

---

## 5. Test gates (this campaign)

| Gate | Result |
| --- | --- |
| Offline `make test` | PASS 56/56 |
| All-models short+long API | PASS 10/10 |
| Real-world / continuous / concurrency API | **PASS 20/20** |
| DSH harness minimal+standard | **BLOCKED** (headless hangs while `dsh web` is up; Postman/API cover same matrix) |
| Vision simple+complicated | **PASS 8/8** |
| ~10k-token long prompt builders + 0.8B smoke | **PASS** |
| Postman collection update | **Done** (`postman/`) |
| Agent rule: all models + both presets + real-world + vision | Updated |
| Browser | DSH UI reachable; BrowserSkill extension not connected |
| Report | this file |

---

## 6. Scripts

| Make target | Script |
| --- | --- |
| `make test` | `test/run.sh` |
| `make test-models` | `test/scripts/all_models_prompt_contract.py` |
| `make test-realworld` | `test/scripts/realworld_api_contract.py` |
| `make test-dsh` | `test/scripts/dsh_harness_contract.py` |
