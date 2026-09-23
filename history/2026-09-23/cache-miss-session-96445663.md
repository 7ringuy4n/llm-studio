# Cache miss on multi-turn session (HF multimodal)

**Session:** `session-96445663-45dd-4694-bedd-733b78f67079`  
**When:** 2026-09-23 ~09:44–09:50 UTC  
**Symptom:** Same DSH conversation / growing prompt, `cache_hit_percent` always `0.0`.

## Not the cause

- Session affinity **worked**: all 9 turns share the same `session_id` (DSH sent
  `X-Session-ID` / openrouter-style affinity).
- Not a broken OpenObserve metric for this path — API JSONL matches.

## Root cause

Model was **`Qwen/Qwen3.5-0.8B`** with `MODEL_BACKEND=multimodal` (Hugging Face
Transformers). Cross-request **prompt prefix** reuse (`LlamaRAMCache` /
`MODEL_KV_CACHE_BYTES`) is wired **only for `backend=gguf`**.

HF path uses `use_cache=True` for **within-generation** KV only
(`api/model_runtime.py`); each new HTTP request re-tokenizes and re-prefills
the full prompt. `cached_prompt_tokens` stays `0`; response header is
`X-KV-Cache: enabled; scope=generation` (not `prompt-and-generation`).

## Evidence (VPS `requests.jsonl`)

| Turn | input_tokens | cached | cache% | first_token_ms |
| --- | ---: | ---: | ---: | ---: |
| 1 | 444 | 0 | 0 | 1403 |
| 2 | 477 | 0 | 0 | 1658 |
| … | … | 0 | 0 | … |
| 9 | 2234 | 0 | 0 | 10384 |

First-token latency scales with prompt size → full re-prefill.

Historical: **153/153** completed `Qwen3.5-0.8B` generations on this VPS have
`cached_input_tokens=0`. GGUF models show non-zero cache samples.

## Live probe (same day)

| Case | Model | Turn2 cache% | `X-KV-Cache` |
| --- | --- | ---: | --- |
| 08b-t2 | Qwen3.5-0.8B | **0.0** | `scope=generation` |
| gguf-t2 | Qwen3-8B | **25.71** | `scope=prompt-and-generation` |

## Fix direction

- **Expected today:** use a **GGUF** living model for multi-turn prefix cache hits.
- Do **not** treat 0% on 0.8B/2B multimodal as an OpenObserve or session bug.
- Optional later: HF StaticCache / prefix reuse across requests (large feature;
  RAM-sensitive on 16 GiB). Prefer documenting + clearer ops guidance first.
