# Verification

Release-verification contract for LLM Studio (Hermes-style `test/` layout).
All offline units and gates live under this folder (merged former `tests/`).

## Layout

| Path | Purpose |
|---|---|
| `README.md` | Verification contract (this file). |
| `REPORT.md` | Index of latest run summaries; update after labs. |
| `run.sh` | Offline static gate with `running test case N/M`. |
| `run_all.sh` | Static gate + focused Python units. |
| `scripts/` | Unit and live contract scripts. |
| `scripts/prompt_length_contract.py` | Live **short** + **long** prompt chat. |
| `../scripts/perf_matrix.py` | Reasoning-effort / first-token / cache matrix. |
| `../docs/perf-results/` | Sanitized perf JSONL + comparison tables. |
| `reports/` | Optional generated lab evidence (no secrets). |

## 1. Safety

- Read `docs/CHANGELOG.md`, `docs/HISTORY.md`, and `history/task_on_progress.md`
  before changing a live VPS.
- Follow `rule/AGENT_RULES.md`. Never commit or print `LLM_STUDIO_API_KEY`.
- Do not attach Hermes networks, volumes, or the Docker socket.

## 2. Outcomes

| Result | Meaning |
|---|---|
| `PASS` | Assertions and contracts succeed. |
| `FAIL` | Wrong status, schema, timing, isolation, or correctness. |
| `SKIP` | External dependency unavailable with proven reason. |
| `BLOCKED` | Missing authorization or operator state. |

## 3. Offline gate

```bash
make test
# or
./test/run_all.sh
```

Focused units under `test/scripts/`:

| Script | Covers |
|---|---|
| `dsh_config_unit.py` | DSH YAML export shape |
| `gguf_runtime_unit.py` | GGUF load kwargs, cache, `/no_think`, timing |
| `model_management_unit.py` | Catalog / activate helpers |
| `tool_calling_unit.py` | Tools / reasoning_effort schema |
| `tracing_unit.py` | Affinity headers, cache %, first/last token |

## 4. Live / lab gates

Require VPN reachability and `LLM_STUDIO_API_KEY` in the environment.

**All living models** (short + long each) — mandatory for release labs:

```bash
set -a && source .env && set +a
export LLM_STUDIO_TEST_BASE_URL=http://10.8.0.1:18080/v1
python3 test/scripts/all_models_prompt_contract.py
```

DeepSeek Harness (headless, all homelab models, short + long; presets
`minimal`, `minimal-web`, `standard`):

```bash
make test-dsh
# or
python3 test/scripts/dsh_harness_contract.py
```

Reasoning-effort **cache hit + miss** (same prefix, switch effort):

```bash
make test-reasoning-cache
# or
python3 test/scripts/reasoning_cache_contract.py
```

OCR / office docs from `Documents/Work/test docs/OCR` (pdf, docx, md, xlsx,
csv, pptx + jpg/png vision). Override root with `LLM_STUDIO_OCR_ROOT`:

```bash
make test-ocr
# or
python3 test/scripts/ocr_docs_contract.py
```

Single-model API smoke and tool contract:

```bash
python3 test/scripts/prompt_length_contract.py
python3 test/scripts/web_search_contract.py
python3 scripts/perf_matrix.py --label lab --cache-probe \
  --out test/reports/perf-lab.jsonl
```

Browser (Tencent BrowserSkill / `bsk`, else IDE browser): DSH
`http://127.0.0.1:8080` and OpenObserve `http://10.8.0.1:15080` — when the
plan requires UI labs, exercise **all** living models. Never paste secrets.

## 5. Real-world readiness

1. `/health` OK; `/v1/models` lists living models.
2. Short and long prompts return non-empty completions.
3. `max_tokens` up to catalog `max_new_tokens` accepted (not 400).
4. Session affinity stable across model switches in OpenObserve.
5. CPU remains **3.0 / 3 threads** unless a measured experiment says otherwise.

Update `test/REPORT.md` after completing labs.
