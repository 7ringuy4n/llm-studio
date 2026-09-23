# Test report index

Latest verification for LLM Studio. No API keys in this file.

## Model statistic report

[`docs/perf-results/model-statistic-report.md`](../docs/perf-results/model-statistic-report.md) ·
[`docs/perf-results/model-statistic-tables.html`](../docs/perf-results/model-statistic-tables.html)

## Latest results (2026-09-23)

| Gate | Result |
|---|---|
| Offline static `make test` | **PASS 56/56** |
| All-models short+long API | **PASS 10/10** |
| ~10k long smoke (0.8B) | **PASS** |
| Real-world / continuous / concurrency | **PASS 20/20** |
| Vision simple+complicated | **PASS 8/8** |
| OCR Work docs (md/pdf/docx/pptx/xlsx/csv + jpg/png) | **PASS 8/8** on 0.8B (`make test-ocr`) |
| Reasoning-cache warm/switch | **PASS 3/3** on 0.8B (`make test-reasoning-cache`; warm cache% still 0 on multimodal) |
| DSH headless minimal+standard+minimal-web | **BLOCKED** while `dsh web` up — use BrowserSkill / Postman / API |
| DSH BrowserSkill | **PASS** minimal (0.8B/2B/Llama) + minimal-web (0.8B); **Standard 0.8B BLOCKED** (Deep diving tool loop >2m) |
| Postman collection/env | **Updated** — all-models ~10k, continuous, vision + OCR Work symlink |
| CPU on VPS | `3.0` / `3` |
| API abnormal logs | none in last scan |

## Make targets

| Target | Purpose |
|---|---|
| `make test` | Offline static gate |
| `make test-models` | All living models short + ~10k long |
| `make test-realworld` | Real-world + continuous + concurrency |
| `make test-vision` | Vision simple + complicated |
| `make test-ocr` | Work OCR corpus (pdf/docx/md/xlsx/csv/pptx + images) |
| `make test-reasoning-cache` | Cache hit + miss when switching reasoning_effort |
| `make test-dsh` | DSH headless minimal / minimal-web / standard (blocked while web up) |

## VPS update

See [`docs/17-vps-update-from-main.md`](../docs/17-vps-update-from-main.md).

## VPS deploy verification (2026-09-23 afternoon)

Synced cancel + labs code to `/home/tn/llm-studio`, rebuilt `llm-studio-api`.

| Gate | Result |
|---|---|
| Live cancel mid-gen (`POST /v1/generation/cancel`) | **PASS** (HTTP 499) |
| All-models short+long (0.8B) | **PASS 2/2** |
| Reasoning-cache (0.8B) | **PASS 3/3** |
| OCR Work docs (0.8B) | **PASS 8/8** |
| DSH headless harness | **FAIL/timeout** (web profile up; known BLOCKED) |
| DSH BrowserSkill short + Stop | **PASS** UI short; Stop clears UI but **does not abort** upstream chat (API still returned 200 after ~2m). Wire DSH Stop → abort fetch or `POST /v1/generation/cancel`. |
| Post-Stop API smoke | **Timeout** (slot stuck); after `docker compose restart api`, short chat **recover_ok** (~10s). |

## Cache miss session `96445663-…` (2026-09-23)

| Check | Result |
|---|---|
| Session affinity | **OK** — 9 turns, one `session-96445663-…` |
| Model / backend | `Qwen/Qwen3.5-0.8B` / **multimodal (HF)** |
| `cache_hit_percent` | **0.0 every turn** (expected: no LlamaRAMCache) |
| Confirm 0.8B t2 | **0%** (`scope=generation`) |
| Confirm GGUF 8B t2 | **25.71%** (`scope=prompt-and-generation`) |

Detail: [`history/2026-09-23/cache-miss-session-96445663.md`](../history/2026-09-23/cache-miss-session-96445663.md).

