# DSH web — Standard-mode continuous compact flood (homelab)

Rules for BrowserSkill (bsk) labs that prove whether DeepSeek Harness **auto-compacts** context under continuous sends. Companion to [`TEST_STRATEGY.md`](./TEST_STRATEGY.md) and [`AGENT_RULES.md`](./AGENT_RULES.md).

## 1. Purpose

- Continuously send user turns in **DSH web** (not headless) until the UI shows **compaction**, **CONTEXT_WINDOW overflow**, or a hard request failure.
- Record whether Standard mode can compact before overflow.
- Default target: **homelab** `Qwen/Qwen3.5-0.8B` (VPN llm-studio) so Vast GPU catalog cycles are not blocked.

## 2. Mode rules (critical)

| Mode | Compaction | Use for compact flood? |
|------|------------|------------------------|
| **Standard** | Present (full agent) | **Required** for § compact proof |
| Minimal | **Absent** (persona `complete` / no compaction) | Negative control only |
| Minimal + Web | Shell + web tools; not the compact SoT | Optional after Standard |

Never claim “compact works” from a Minimal session.

## 3. Harness

```bash
# Requires: dsh web on :8080, bsk daemon + extension, VPN to homelab
DSH_COMPACT_MODE=standard \
DSH_COMPACT_MODEL='Qwen/Qwen3.5-0.8B' \
DSH_COMPACT_MAX_TURNS=30 \
DSH_COMPACT_CHUNK_REPS=100 \
bash test/scripts/dsh_web_compact_flood.sh
```

- Progress: `running test case N/M: dsh-web/compact-flood/standard/turn-N`
- Artifact: `docs/perf-results/dsh-web-compact-flood.jsonl`
- Fill payloads must stay **≤ ~3500 chars** per turn (bsk fill stability); grow context via **many turns**, not one giant paste.

## 4. Pass / fail criteria

| Outcome | Meaning |
|---------|---------|
| `saw_compact: true` | **PASS** — UI showed **Context compaction** / compacted conversation / Compacting context |
| `saw_overflow: true` without compact | **PARTIAL / FAIL compact** — window exceeded; note if “could not produce a useful summary” |
| `saw_error: true` (Request failed) only | Investigate provider/VPN; do not score as compact |
| Hits `MAX_TURNS` with neither | **INCONCLUSIVE** — raise chunk reps or lower model `contextWindow` for the probe |

Do **not** treat the substring `compact` alone as success (false positives). Require the phrases above.

Align DSH model `contextWindow` with the provider (homelab catalog / Vast `num_ctx`). Mismatch causes early overflow (see 27B 32k vs 64k history).

## 5. Coverage expectations

When lab-temp asks for compact proof:

1. Run Standard-mode flood on **homelab** (this rule).
2. Optionally repeat on **Vast** current resident model after catalog cycle parks a model.
3. Log results into `model-statistic-report.md` (DSH auto-compact section).
4. Do **not** commit Vast public host:port; use SSH local-forward for GPU provider.

## 6. Related scripts

| Script | Role |
|--------|------|
| `test/scripts/dsh_web_compact_flood.sh` | Continuous Standard-mode flood |
| `test/scripts/dsh_web_full_matrix.py` | Modes × efforts × short/coding |
| `test/scripts/dsh_harness_contract.py` | Headless preset smoke (not compact SoT) |
