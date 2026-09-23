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

## 2. Short + long prompt lab (all living models)

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
Gate: `make test-vision` — **PASS 8/8**.

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
| Browser DSH web (bsk) minimal / +web / standard × Vast short | **PASS 3/3** |
| Vast catalog cycle (pull→lab→rm each models.json) | **IN PROGRESS** (`vast-all-models-cycle.jsonl`) |
| Report | this file |

---

## 9. CPU VPS full statistic lab

**Host:** 4 vCPU · 16 GiB · `LLM_STUDIO_API_CPUS=3.0` · one resident model  
**Artifact:** `docs/perf-results/all-models-full-lab.jsonl` · **38 rows · 32 OK**  
**Gap:** `Qwen/Qwen3-1.7B` → HTTP **404** (not in live `MODEL_ALLOWED_MODELS`).

| Model | Case | OK | in/out | Cache% | First ms | Last ms | Wall s | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen3.5-0.8B | short | Y | 17/16 | 0 | 1057 | 2746 | 11.5 | |
| Qwen3.5-0.8B | long-2k | Y | 2671/16 | 0 | 14376 | 16842 | 17.0 | |
| Qwen3.5-0.8B | cache-warm | Y | 46/16 | **0** | 302 | 2301 | 2.5 | HF: no cross-request cache |
| Qwen3.5-0.8B | ocr-md | Y | 186/31 | 0 | 792 | 4763 | 4.9 | city **PASS** |
| Qwen3.5-0.8B | vision | Y | 803/17 | 0 | 7194 | 9407 | 9.9 | |
| Qwen3.5-0.8B | concurrency-2 | Y | — | — | — | — | 1.1 / 2.1 | queued |
| Qwen3.5-2B | short | Y | 17/16 | 0 | 2903 | 6641 | 15.4 | |
| Qwen3.5-2B | long-2k | Y | 2671/16 | 0 | 22802 | 26887 | 27.1 | |
| Qwen3.5-2B | cache-warm | Y | 46/16 | **0** | 450 | 3553 | 3.7 | HF |
| Qwen3.5-2B | ocr-md | Y | 186/50 | 0 | 1396 | 13956 | 14.2 | city **PASS** |
| Qwen3.5-2B | vision | Y | 803/24 | 0 | 17643 | 23549 | 24.0 | |
| Qwen3-1.7B | *all* | **N** | — | — | — | — | — | not in `MODEL_ALLOWED_MODELS` |
| Qwen3-8B | short | Y | 17/5 | 0 | 872 | 1429 | 16.9 | |
| Qwen3-8B | long-2k | Y | 2671/6 | 0.11 | **138604** | 139641 | 141.4 | prompt-eval bound |
| Qwen3-8B | cache-warm | Y | 46/6 | **100** | 155 | 830 | 1.0 | GGUF prefix |
| Qwen3-8B | ocr-md | Y | 174/9 | 1.72 | 11530 | 12782 | 13.2 | city **PASS** |
| DeepSeek-R1 7B | long-2k | Y | 2666/16 | 0.08 | 127106 | 129092 | 129.9 | |
| DeepSeek-R1 7B | cache-warm | Y | 36/16 | **100** | 118 | 1913 | 2.1 | |
| DeepSeek-R1 7B | ocr-md | Y | 169/64 | 1.18 | 8461 | 15424 | 15.7 | city **FAIL** |
| Llama 3.1 8B | long-2k | Y | 2538/2 | 1.18 | 129531 | 129841 | 131.1 | |
| Llama 3.1 8B | cache-warm | Y | 60/2 | **100** | 110 | 358 | 0.6 | |
| Llama 3.1 8B | ocr-md | Y | 196/8 | 15.31 | 9460 | 10326 | 10.8 | city **PASS** |

**Takeaway:** GGUF cache-warm first-token drops to ~0.1–0.2s; HF stays 0% cache. Long ~2k on 8B-class GGUF is ~130–140s TTFT on this CPU host — prefer Vast for that latency class.

---

## 9b. Vast GPU full statistic lab (catalog cycle + 27B)

**Host:** Vast.ai GPU instance **32 GB VRAM** · Ollama OpenAI `/v1` via SSH local-forward (do not publish public host:port)  
**Harness:** `test/scripts/vast_catalog_cycle_lab.py` · **Artifact:** `docs/perf-results/vast-all-models-cycle.jsonl` (models 1–6 **50/50 OK**)  
**27B:** metrics from dedicated lab `vast-qwen38-27b-lab.jsonl` (**9/9 PASS**, `qwen3.8:27b-ctx64k`, ~20–22 GiB VRAM @ 64k); catalog-cycle suite rows merge into the same artifact when available.

### Per-case metrics (GPU)

| Model | Case | OK | in/out | Cache% | Wall s | VRAM MiB | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Qwen3.5-0.8B | short | Y | 15/16 | 0 | 7.1 | **2714** | Ollama `qwen3.5:0.8b` |
| Qwen3.5-0.8B | long-2k | Y | 2669/16 | 0 | 6.3 | 2716 | vs CPU ~17s / 14s TTFT |
| Qwen3.5-0.8B | cache-warm | Y | 29/16 | **86** | 9.2 | 2716 | Ollama prefix cache |
| Qwen3.5-0.8B | long-8k | Y | 10558/16 | 5.9 | 9.2 | 2748 | |
| Qwen3.5-0.8B | ocr-md | Y | 184/64 | 0 | 5.5 | 2748 | city weak on this tag |
| Qwen3.5-0.8B | vision | Y | 806/64 | 0 | 13.9 | 2748 | |
| Qwen3.5-0.8B | concurrency-2 | Y | — | — | 4.7 / 6.7 | 2782 | |
| Qwen3.5-0.8B | coding | Y | 22/32 | 0 | 6.0 | 2782 | `accuracy_coding` **FAIL** — not for coding |
| Qwen3.5-2B | short | Y | 15/16 | 0 | 6.4 | **4452** | |
| Qwen3.5-2B | long-2k | Y | 2669/16 | 0 | 8.0 | 4454 | vs CPU ~27s |
| Qwen3.5-2B | cache-warm | Y | 29/16 | **86** | 11.7 | 4454 | |
| Qwen3.5-2B | long-8k | Y | 10558/16 | 5.9 | 14.9 | 4512 | |
| Qwen3.5-2B | vision | Y | 806/64 | 0 | 9.7 | 4512 | |
| Qwen3.5-2B | coding | Y | 22/32 | 0 | 9.9 | 4552 | `accuracy_coding` **FAIL** — not for coding |
| Qwen3-1.7B | short | Y | 15/16 | 20 | 9.2 | **6316** | works on Vast (CPU VPS allow-list gap) |
| Qwen3-1.7B | cache-warm | Y | 29/16 | **97** | 12.4 | 6332 | |
| Qwen3-1.7B | long-8k | Y | 10558/16 | 25 | 18.2 | 6378 | |
| Qwen3-1.7B | coding | Y | 21/32 | 14 | 10.0 | 6378 | `accuracy_coding` **FAIL** — not for coding |
| Qwen3-8B | short | Y | 15/16 | 20 | 4.8 | **11308** | |
| Qwen3-8B | long-2k | Y | 2669/16 | 0 | **8.8** | 11324 | vs CPU **141s** |
| Qwen3-8B | cache-warm | Y | 29/16 | **97** | 8.0 | 11324 | |
| Qwen3-8B | long-8k | Y | 10558/16 | 25 | 9.7 | 11464 | |
| Qwen3-8B | coding | Y | 21/32 | 14 | 9.6 | 11464 | `accuracy_coding` **FAIL** @ 32 (thinking) — conditional snippets |
| DeepSeek-R1 7B | short | Y | 8/16 | 25 | 5.2 | **8898** | |
| DeepSeek-R1 7B | long-2k | Y | 2662/16 | 0 | **7.2** | 8898 | vs CPU **130s** |
| DeepSeek-R1 7B | cache-warm | Y | 17/16 | **94** | 5.9 | 8898 | |
| DeepSeek-R1 7B | long-8k | Y | 10551/16 | 25 | 7.7 | 9114 | |
| DeepSeek-R1 7B | coding | Y | 14/32 | 14 | 4.9 | 9114 | `accuracy_coding` **FAIL** @ 32 (thinking) — conditional |
| Llama 3.1 8B | short | Y | 15/2 | 33 | 5.6 | **13644** | |
| Llama 3.1 8B | long-2k | Y | 2513/3 | 0.2 | **6.8** | 13646 | vs CPU **131s** |
| Llama 3.1 8B | cache-warm | Y | 29/3 | **97** | 11.9 | 13646 | |
| Llama 3.1 8B | long-8k | Y | 9938/4 | 25 | 9.2 | 13824 | |
| Llama 3.1 8B | ocr-md | Y | 171/6 | 2.9 | 7.8 | 13824 | city **PASS** |
| Llama 3.1 8B | coding | Y | 21/5 | 33 | 5.1 | 13824 | coding **PASS** — **recommended ≤8B** |
| **Qwen3.8-27B** | short | Y | 15/37 | 0 | 13.3 | **~20–22k** | dedicated lab; ctx64k |
| **Qwen3.8-27B** | cache-warm | Y | 48/32 | **92** | 2.9 | ~20–22k | Ollama prefix |
| **Qwen3.8-27B** | long-2k | Y | 2669/32 | 0 | 7.3 | ~20–22k | |
| **Qwen3.8-27B** | long-8k | Y | 10558/32 | 20 | 14.4 | ~20–22k | |
| **Qwen3.8-27B** | ocr-md | Y | 190/47 | 0 | 4.3 | ~20–22k | city **PASS** |
| **Qwen3.8-27B** | vision | Y | 808/101 | 0 | 7.2 | ~20–22k | |
| **Qwen3.8-27B** | concurrency-2 | Y | — | — | 2.4 / 4.1 | ~20–22k | |
| **Qwen3.8-27B** | tools-web_search | Y | — | — | 3.0 | ~20–22k | `tool_calls` |
| **Qwen3.8-27B** | coding | Y | 22/32 | 0 | 8.3 | ~22.7k | cycle gate **FAIL** @ 32; DSH showed answer — **primary coding agent** |

### Measured VRAM / HDD / recommended GPU class

| Model | Ollama tag | Measured VRAM (resident) | Measured HDD (Ollama pull) | Min GPU | Comfortable HDD |
| --- | --- | --- | --- | --- | --- |
| Qwen3.5-0.8B | `qwen3.5:0.8b` | ~2.7 GB | **1.0 GB** | 6–8 GB | ≥5 GB free |
| Qwen3.5-2B | `qwen3.5:2b` | ~4.5 GB | **2.7 GB** | 8 GB | ≥8 GB free |
| Qwen3-1.7B | `qwen3:1.7b` | ~6.3 GB | **1.4 GB** | 8 GB | ≥5 GB free |
| Qwen3-8B | `qwen3:8b` | ~11.3 GB | **5.2 GB** | 12 GB | ≥12 GB free |
| DeepSeek-R1 7B | `deepseek-r1:7b` | ~9.0 GB | **4.7 GB** | 10 GB | ≥12 GB free |
| Llama 3.1 8B | `llama3.1:8b` | ~13.6 GB | **4.9 GB** | 14 GB | ≥12 GB free |
| **Qwen3.8 27B** | `qwen3.8:27b` (+ ctx64k) | **~20–22 GB** @ 64k | **~17 GB** (16 GB weights + ~1 GB extras) | **24 GB** | **≥40 GB** container (32 GB fills) |

**HDD notes (Vast):** one-model-at-a-time cleanup kept peak use ~17 GB weights on a **32 GB** overlay; concurrent pulls or leftover blobs fill the disk. Prefer **≥40 GB** disk when hosting 27B.

**HDD notes (CPU VPS `/opt/data/llm-studio`):** HF safetensors + GGUF caches are larger than Ollama Q4 pulls (multimodal 0.8B/2B + three ~5 GB GGUFs easily **≥40–80 GB** with HF hub cache). Keep **≥100 GB** when OO + all catalog weights coexist; unload/delete unused revisions.

**Takeaway:** Vast cuts 8B-class long-2k wall from ~130–140s (CPU) to ~7–9s. Keep ≤8B on CPU VPS for cost; rent GPU for latency, vision speed, or **27B**. Coding: **Llama 3.1 8B** (≤8B) or **27B** (agent); skip 0.8B/1.7B/2B — see §8.1b.

---

## 10. Vast catalog cycle (deploy → lab → cleanup)

**Procedure:** delete previous Ollama weights → `ollama pull` mapped tag → warm → suite (short/cache/long/OCR/vision?/coding/concurrency) → `ollama rm` → next  
**Harness:** `test/scripts/vast_catalog_cycle_lab.py` · **Artifact:** `docs/perf-results/vast-all-models-cycle.jsonl`  
**Map:** 0.8B→`qwen3.5:0.8b`, 2B→`qwen3.5:2b`, 1.7B→`qwen3:1.7b`, 8B→`qwen3:8b`, R1→`deepseek-r1:7b`, Llama→`llama3.1:8b`, 27B→`qwen3.8:27b` (+ ctx64k alias)  
**Coverage:** models 1–6 in cycle JSONL; **27B** also covered by dedicated lab (**9/9** — §9b / §7).

Full case table + VRAM: **§9b**.

---

## 7. Vast GPU lab — Qwen3.8 27B

**Host:** Vast.ai GPU instance **32 GB VRAM** · Ollama `qwen3.8:27b-ctx64k` (`num_ctx=65536`)  
**API:** OpenAI-compatible Ollama on the GPU instance (set `VAST_TEST_BASE_URL` / DSH `vast.baseURL` locally; do not commit host:port)  
**Catalog:** `Qwen/Qwen3.8-27B` with `deployment: vast-ollama` (not loaded on CPU VPS)  
**Artifact:** `docs/perf-results/vast-qwen38-27b-lab.jsonl` · harness `test/scripts/vast_qwen38_27b_lab.py`

| Gate | Result | Tokens in/out | Cached | Wall | Notes |
| --- | --- | --- | --- | --- | --- |
| short | **PASS** | 15/37 | 0 | 13.3s | content `OK` (thinking then answer) |
| cache-cold | **PASS** | 48/32 | 0 | 2.2s | hit length on thinking |
| cache-warm | **PASS** | 48/32 | **44** (~92%) | 2.9s | Ollama prefix cache works |
| long ~2k | **PASS** | 2669/32 | 0 | 7.3s | |
| long ~8–10k | **PASS** | 10558/32 | **2157** | 14.4s | partial prefix reuse |
| OCR md (Work/test docs) | **PASS** | 190/47 | 0 | 4.3s | **Ho Chi Minh City** grounded |
| vision (apple.jpg) | **PASS** | 808/101 | 0 | 7.2s | describes apples/basket |
| concurrency ×2 | **PASS** | — | — | 2.4s / 4.1s | both 200 (serialized on 1 GPU) |
| tools `web_search` required | **PASS** | — | — | 3.0s | `finish_reason=tool_calls` (1 call) |

**VRAM (resident):** ~20–22 GiB / 32 GiB with 64k ctx.  
**Disk:** need ≥40 GB container (32 GB fills with one 17 GB model + downloads).

### DSH auto-compact

Observed on DSH with this Vast model: when prompt hit **32769 > n_ctx 32768** (before ctx64k fix), UI raised `CONTEXT_WINDOW_EXCEEDED` and **compaction failed** (“could not produce a useful summary”). After switching to **`qwen3.8:27b-ctx64k`** + DSH `contextWindow: 65536`, new sessions should avoid the 32k wall. Compact still depends on DSH summarizer quality under tool+image noise — treat as **partial / unreliable**, not a hard guarantee.

---


### DSH Standard-mode continuous compact flood (homelab)

Rules: `rule/DSH_COMPACT_FLOOD.md` · harness `test/scripts/dsh_web_compact_flood.sh` · Cursor rule `.cursor/rules/dsh-compact-flood.mdc`.  
Must use **Standard** mode (Minimal has no compaction). Artifact: `docs/perf-results/dsh-web-compact-flood.jsonl`.  
Detection requires explicit UI phrases (`Context compaction` / compacted conversation), not bare substring `compact`.


## 8. Hardware recommendation (real)

Two deployment lanes: **CPU VPS** (llm-studio, one resident model) and **Vast GPU**
(Ollama OpenAI `/v1`, DSH second provider via SSH local-forward — do not commit
public host:port). Pick per model below.

### 8.1 Per-model — CPU VPS vs Vast (RAM / VRAM / HDD)

| Model | CPU RAM | Vast VRAM (measured) | HDD weights (measured Ollama pull) | CPU VPS HDD (HF/GGUF cache, approx) |
| --- | --- | --- | --- | --- |
| Qwen3.5-0.8B | 4c / **16 GiB** host | **~2.7 GB** | **1.0 GB** | ~2–4 GB HF |
| Qwen3.5-2B | 4c / **16 GiB** | **~4.5 GB** | **2.7 GB** | ~4–6 GB HF |
| Qwen3-1.7B | 4c / **12–16 GiB** | **~6.3 GB** | **1.4 GB** | ~3–5 GB HF |
| Qwen3-8B Q4 | 4c / **16+ GiB** | **~11.3 GB** | **5.2 GB** | ~5 GB GGUF |
| DeepSeek-R1 7B Q4 | 4c / **16+ GiB** | **~9.0 GB** | **4.7 GB** | ~4.5–5 GB GGUF |
| Llama 3.1 8B Q4 | 4c / **16+ GiB** | **~13.6 GB** | **4.9 GB** | ~4.5–5 GB GGUF |
| **Qwen3.8 27B Q4** | **not on 16 GiB CPU** | **~20–22 GB** @ 64k | **~17 GB** | n/a (Vast only) |

| Lane | Min HDD | Comfortable HDD |
| --- | --- | --- |
| CPU VPS (all ≤8B catalog + OO) | 80 GB | **100–120 GB** under `/opt/data/llm-studio` |
| Vast (one model, cleanup between) | 20 GB for ≤8B | **≥40 GB** if pulling **27B** (~17 GB) on a 32 GB overlay |

### 8.1b Coding fit (per catalog model)

Gate: Vast cycle `…/coding` — exact reply `return a + b` (`max_tokens=32`, thinking may burn the budget). Artifact: `vast-all-models-cycle.jsonl` (`accuracy_coding`). DSH Minimal coding spot-check for 27B.

| Model | Lab coding gate | Coding recommendation |
| --- | --- | --- |
| Qwen3.5-0.8B | **FAIL** (empty / `length`) | **Not recommended** — chat/vision only; too small for coding agents |
| Qwen3.5-2B | **FAIL** (empty / `length`) | **Not recommended** — chat/vision only; not a coding agent |
| Qwen3-1.7B | **FAIL** (empty / `length`) | **Not recommended** — text smoke / short chat only |
| Qwen3-8B Q4 | **FAIL** @ 32 out (thinking) | **Conditional** — OK for snippets if reasoning **off** and higher `max_tokens`; not the primary coding pick on CPU |
| DeepSeek-R1 7B Q4 | **FAIL** @ 32 out (thinking) | **Conditional** — better for hard reasoning-style coding with a **large** token budget; avoid for exact one-line replies |
| Llama 3.1 8B Q4 | **PASS** (`return a + b`, stop) | **Recommended (≤8B)** — best measured exact coding reply on Vast among catalog ≤8B |
| **Qwen3.8 27B Q4** | Cycle **FAIL** @ 32 out; DSH coding showed `return a + b` | **Recommended (primary coding agent on Vast)** — use enough `max_tokens` / turn thinking down for short exact replies |

**Pick:** daily ≤8B coding → **Llama 3.1 8B**; serious DSH/coding-agent work → **Qwen3.8 27B** on Vast. Do not point coding agents at 0.8B / 1.7B / 2B.

Full dual-lane case + VRAM/HDD tables: §9 (CPU) + §9b (Vast).

### 8.2 Shared host rules

| Lane | Spec | Notes |
| --- | --- | --- |
| CPU VPS (llm-studio) | Keep **`LLM_STUDIO_API_CPUS=3.0` / 3 threads** on 4 vCPU | Leave 1 core for OO / OTel / Traefik / Docker |
| Vast (any catalog model) | On-demand GPU; container disk **≥40 GB** if pulling ≥17 GB weights | One Ollama model resident; unload/delete blobs before switching large pulls |
| DSH | `contextWindow` must match runtime ctx (`num_ctx` / catalog `context_tokens` room) | Compact is **partial** — fails if overflowed before summarizer runs |
| Cache | GGUF / Ollama: cross-request prefix cache **yes**; HF multimodal: **0%** across HTTP turns | Same on CPU or Vast for HF |

### 8.3 Vast sizing cheat-sheet (all models)

| VRAM class | Fits well | Avoid |
| --- | --- | --- |
| 8–12 GB | 0.8B–2B HF; light Q4 7–8B at modest `num_ctx` | 27B; large `num_ctx` on 8B |
| 16 GB | All ≤8B Q4 + HF 2B at useful ctx | 27B at 64k |
| 24 GB | 27B Q4 at ≤32k ctx | Prefer 32 GB for **64k** |
| **32 GB** | **27B Q4 @ 64k** (measured) + room to swap smaller models | Filling disk with partial pulls |

**Recommendation:** keep daily chat/tools on CPU VPS for ≤8B; rent Vast when you need (a) **27B**, (b) **long context** latency, or (c) **vision/OCR** speed. Point DSH `vast` at a **localhost SSH forward**, not a committed public URL.

---

## 11. Scripts

| Make target | Script |
| --- | --- |
| `make test` | `test/run.sh` |
| `make test-models` | `test/scripts/all_models_prompt_contract.py` |
| `make test-realworld` | `test/scripts/realworld_api_contract.py` |
| `make test-dsh` | `test/scripts/dsh_harness_contract.py` |
| *(manual Vast cycle)* | `test/scripts/vast_catalog_cycle_lab.py` |
| *(manual Vast 27B)* | `test/scripts/vast_qwen38_27b_lab.py` |
| *(manual VPS full)* | `test/scripts/full_model_statistic_lab.py` |
| *(manual ctx ladder)* | `test/scripts/context_max_ladder_lab.py` |
| *(manual coding)* | `test/scripts/coding_sim_lab.py` |
| *(manual DSH web)* | `test/scripts/dsh_web_full_matrix.py` |
