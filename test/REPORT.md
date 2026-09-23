# Test report index

Latest verification for LLM Studio. No API keys in this file.

## Model statistic report

[`docs/perf-results/model-statistic-report.md`](../docs/perf-results/model-statistic-report.md)

## Latest results (2026-09-23)

| Gate | Result |
|---|---|
| Offline static `make test` | **PASS 56/56** |
| All-models short+long API | **PASS 10/10** |
| ~10k long smoke (0.8B) | **PASS** (see `test/reports/all-models-prompt-perf.json` after smoke) |
| Real-world / continuous / concurrency | **PASS 20/20** |
| Vision simple+complicated | **PASS 8/8** |
| DSH headless minimal+standard | **BLOCKED** — `dsh --profile headless` hangs with web profile online; use Postman / API labs + DSH web UI |
| Postman collection/env | **Updated** — all-models ~10k, continuous, vision folders + fixtures |
| CPU on VPS | `3.0` / `3` |
| API abnormal logs | none in last scan |
| BrowserSkill | BLOCKED — 0 browsers; IDE browser reached DSH UI |

## Make targets

| Target | Purpose |
|---|---|
| `make test` | Offline static gate |
| `make test-models` | All living models short + ~10k long |
| `make test-realworld` | Real-world + continuous + concurrency |
| `make test-vision` | Vision simple + complicated |
| `make test-dsh` | DSH headless minimal+standard (blocked while web up) |
