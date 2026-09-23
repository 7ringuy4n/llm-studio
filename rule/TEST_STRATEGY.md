# LLM Studio test strategy

Adapted from Work/rule `TEST_STRATEGY.md` for this repository.

## 1. Purpose

Prove **invariants**, not raw test count:

- Isolation (no Hermes / no Docker socket)
- Catalog and max-token ceilings
- GGUF load / cache / thinking flags
- Session affinity and tracing headers
- Tool-call contract (`web_search` emission only — DSH executes search)
- Short-prompt and long-prompt chat behavior on live API **for every living model**
- DSH harness headless short+long for every `homelab` model
- **DSH web Standard-mode continuous compact flood** (homelab / bsk) —
  see `rule/DSH_COMPACT_FLOOD.md`
- CPU quota defaults (3.0 / 3 threads)

## 2. Layout

```text
test/
├── README.md          # verification contract
├── REPORT.md          # latest run index
├── run.sh             # offline static gate (N/M progress)
├── run_all.sh         # static + focused units
├── scripts/           # unit and live contract scripts
│   ├── dsh_config_unit.py
│   ├── gguf_runtime_unit.py
│   ├── model_management_unit.py
│   ├── tool_calling_unit.py
│   ├── tracing_unit.py
│   ├── web_search_contract.py
│   └── prompt_length_contract.py   # short + long prompts (live)
└── reports/           # optional lab evidence (no secrets)
```

## 3. Invariant-first

Before adding tests: what must always be true? Which failure modes are
untested? Do not weaken assertions to obtain a pass. If a live failure
reveals a core bug, fix source of truth and re-run.

## 4. Progress reporting

Runners must print `running test case N/M: <name>` so operators can track
coverage during long labs.
