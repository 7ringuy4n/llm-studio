# CPU performance tuning (4 vCPU / 16 GiB)

Baseline reference: [`model-statistic 2.docx`](/home/tringuyen/Documents/model-statistic%202.docx)
(max_tokens=512, all reasoning efforts, API capped at **3 CPU** on a **4-vCPU** host).

Raw runs: [perf-results/](perf-results/).

## Best practices (this stack)

| Lever | Practice | Why |
| --- | --- | --- |
| API `cpus` vs host | Prefer **3.0** on a 4-vCPU VPS | Leaves 1 core for OS + OpenObserve; full 4 often regresses under load |
| `LLM_STUDIO_CPU_THREADS` | Match the API CPU quota | Oversubscription thrashes; undersubscription leaves cores idle |
| `OMP` / `MKL` / `OPENBLAS` threads | Same as CPU threads (compose) | Stops BLAS from spawning extra threads |
| Concurrency | Keep `MAX_CONCURRENT_REQUESTS=1` | One generation fills the cores; queue instead of fighting |
| GGUF `n_batch` / `n_ubatch` | **512** | Faster prompt eval |
| `use_mmap` | **true** | Faster load, less anonymous RAM |
| `use_mlock` | **false** on 16 GiB | Avoid pinning large weights when RAM is tight |
| `MODEL_KV_CACHE_BYTES` | **2 GiB** LlamaRAMCache | Prefix reuse → huge first-token win on turn 2+ |
| GGUF context | Cap **32768** | Cuts KV memory and prompt cost |
| Reasoning effort | Use **off** when format is fixed; **low/medium** for hard math | Extra thinking burns output tokens and last-token time |
| Warmth / cache | Hit each model once before UX timing | Cold load dominates first token |
| Clients | Prefer SSE when UX cares about first token | Same compute; earlier visible tokens |

### Env knobs

```bash
LLM_STUDIO_API_CPUS=3.0          # recommended; try 4.0 only after measuring
LLM_STUDIO_CPU_THREADS=3
MODEL_GGUF_N_BATCH=512
MODEL_GGUF_N_UBATCH=512
MODEL_GGUF_USE_MMAP=true
MODEL_GGUF_USE_MLOCK=false
MODEL_KV_CACHE_BYTES=2147483648
```

```bash
cd ~/llm-studio
./scripts/set_api_cpus.sh 3   # or 4
LLM_STUDIO_TEST_BASE_URL=http://10.8.0.1:18080/v1 \
  python3 scripts/perf_matrix.py --label cpus3 --cache-probe \
  --out /tmp/perf-cpus3.jsonl
```

## What improved vs baseline doc

Same shape: apples `15+32` → `FINAL=47`, `max_tokens=512`, efforts
`off|low|medium|high|xhigh|max`.

| Change | Effect |
| --- | --- |
| Explicit `n_batch=512` + mmap | Faster GGUF prompt path |
| OMP/MKL/OPENBLAS pinned to thread count | Less hidden oversubscription |
| Prefix RAM cache (already 2 GiB) measured | Turn-2+ first token often **0.1–0.5s** at **87–100%** cache hit |
| `set_api_cpus.sh` | Clean A/B of 3 vs 4 |

Notable vs `model-statistic 2.docx` (3-CPU era, different prompt but same budget):

| Model / mode | Baseline total | After (3 vCPU) total | Notes |
| --- | --- | --- | --- |
| Qwen3.5-0.8B off | 13.35s | **6.30s** | First token 1.00s → **0.36s** |
| Qwen3.5-2B off | 148.39s (bad loop) | **13.74s** | Now exact `FINAL=47` |
| Qwen3-8B off | 18.60s | 25.20s | Cold load variance; cached low = **23s** with **87.5%** hit |
| DeepSeek-R1 off | 35.33s | 41.14s | Exact format now Yes; cached efforts ~**26–28s** |
| Llama off | 17.61s / wrong | **17.00s** exact | Cached efforts **~0.6s** (prefix hit) |

Math: **30/30** correct on both new matrices (baseline was 23/30).

## After-improvement tables (3 vCPU, recommended)

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
| Llama 3.1 8B | low–max | Yes / Yes | 73/3 | 100.0 | ~0.11–0.13s | ~0.45–0.54s | **~0.6s** |

Cache probe (Qwen3-8B): first call first-token **5.2s** (0% hit) → second **0.34s** (**100%** hit).

## 3 vCPU vs 4 vCPU

| Metric | 3 vCPU | 4 vCPU |
| --- | --- | --- |
| Successful cells | 30/30 | 30/30 |
| Math correct | 30/30 | 30/30 |
| Exact `FINAL=47` | 24/30 | 24/30 |
| Mean total | **38.7s** | 44.7s |
| Mean first token | 1.03s | **0.72s** |
| Paired Δ total (4 vs 3) | — | **+25.6%** (4 slower on average) |

Cold GGUF **off** is usually faster on 4 cores (e.g. Qwen3-8B 25.2s → 19.5s, first 6.9s → 3.9s), but several long reasoning runs on 4 cores blew out (Qwen3-8B high/xhigh/max **84–185s**) when the host had no spare core for Docker/OpenObserve.

**Recommendation:** keep **`LLM_STUDIO_API_CPUS=3.0`** / **`LLM_STUDIO_CPU_THREADS=3`**. Use 4 only for isolated cold-load experiments, not as the always-on default.

Full paired Δ table: [perf-results/comparison.md](perf-results/comparison.md).

## Reasoning-effort guidance

| Effort | When to use | Perf note |
| --- | --- | --- |
| `off` | Short answers, tools, exact formats | Lowest tokens; best latency |
| `low` / `medium` | Hard math / planning on Qwen3 / R1 | Sweet spot on this VPS |
| `high` / `xhigh` / `max` | Rarely | Same boolean “thinking” for many GGUF paths; burns the 512 budget on 0.8B |

Llama does **not** support thinking; starred efforts in the baseline were no-ops. With a clear `FINAL=` prompt it still answers correctly and caches extremely well.
