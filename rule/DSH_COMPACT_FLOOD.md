# DSH web — Standard-mode continuous max-context compact flood

Rules for BrowserSkill (bsk) labs that prove whether DeepSeek Harness **auto-compacts**
or **continues** under a coding-agent-like session that grows toward max context.
Companion to [`TEST_STRATEGY.md`](./TEST_STRATEGY.md) and [`AGENT_RULES.md`](./AGENT_RULES.md).

API (non-UI) continuous growth SoT: `test/scripts/coding_agent_max_ctx_compact_lab.py`.

## 1. Purpose

- Continuously send **coding-agent style** user turns in **DSH web** (not headless)
  until the UI shows **compaction**, **CONTEXT_WINDOW overflow**, hard failure, or
  the session **keeps working** near the configured `contextWindow`.
- Grow context via **many turns** (and optional larger chunks) toward the model's
  practical max — not a single giant paste.
- After first compact (if any), send **continue turns** to verify the agent can
  still use the session (post-compact usability).

## 2. Mode rules (critical)

| Mode | Compaction | Use for compact/continue proof? |
|------|------------|----------------------------------|
| **Standard** | Present (full agent) | **Required** |
| Minimal | **Absent** | Negative control only |
| Minimal + Web | Not compact SoT | Optional after Standard |

Never claim “compact works” from a Minimal session.

## 3. Harness

```bash
# Requires: dsh web on :8080, bsk daemon + extension, provider reachable
# Per-model: DSH_COMPACT_CATALOG_KEY picks THAT model's test_context_tokens
# (no shared ctx4k/32k suite across models).
DSH_COMPACT_MODE=standard \
DSH_COMPACT_CATALOG_KEY='Qwen/Qwen3.5-9B' \
DSH_COMPACT_MODEL='qwen3.5:9b-ctx128k (Vast 9B max-ctx lab)' \
DSH_COMPACT_CONTINUE_AFTER=5 \
DSH_COMPACT_KIND=coding-agent \
bash test/scripts/dsh_web_compact_flood.sh
```

- Progress: `running test case N/M: dsh-web/coding-max-ctx/{mode}/turn-N`
- Artifact: `docs/perf-results/dsh-web-compact-flood.jsonl`
- Fill payloads stay **≤ ~3500 chars** per turn (bsk fill stability).
- Align DSH `contextWindow` and Ollama `num_ctx` to **that model's**
  `ollama_num_ctx` / `test_context_tokens` (see `configs/models.json`).
  Example: 9B → 131072; 27B → 65536. Do **not** reuse one reduced window
  for every model.

OpenAI/Ollama continuous max-ctx (no UI compact signal):

```bash
VAST_TEST_BASE_URL=http://127.0.0.1:11434/v1 \
VAST_CYCLE_MODELS='Qwen/Qwen3.5-9B' \
python3 test/scripts/coding_agent_max_ctx_compact_lab.py
```

OpenCode (temporary install) — same per-model rule:

```bash
CATALOG_KEY='Qwen/Qwen3.5-9B' bash test/scripts/opencode_compact_flood.sh
CATALOG_KEY='Qwen/Qwen3.8-27B' bash test/scripts/opencode_compact_flood.sh
```

## 4. Pass / fail criteria

| Outcome | Meaning |
|---------|---------|
| `saw_compact: true` then continue turns OK | **PASS compact+continue** |
| `saw_compact: true` then continue fails | **PARTIAL** — compact fired, session unusable |
| `saw_overflow: true` without compact | **FAIL compact** — window exceeded; note summary errors |
| Keeps answering near max with neither compact nor overflow | **CONTINUE_OK** — no auto-compact observed; provider still usable |
| `saw_error: true` only | Investigate provider/VPN; do not score as compact |
| Hits `MAX_TURNS` with neither | **INCONCLUSIVE** — raise chunk reps or lower DSH `contextWindow` |

Do **not** treat the substring `compact` alone as success. Require:
`Context compaction` / `compacted the conversation` / `Compacting context`.

Align DSH model `contextWindow` with **that model's** provider `num_ctx` /
`test_context_tokens` — never one common reduced window for all models.

## 5. Coverage expectations

1. Standard-mode coding-agent flood on **homelab** (this rule).
2. API continuous max-ctx lab for each catalog model under test (Vast or VPS).
3. Optionally repeat DSH flood on **Vast** resident model after a cycle parks one.
4. Log into `model-statistic-report.md` (DSH auto-compact / continue section).
5. Do **not** commit Vast public host:port; use SSH local-forward.

## 6. Related scripts

| Script | Role |
|--------|------|
| `test/scripts/dsh_web_compact_flood.sh` | DSH web continuous coding-agent flood + continue |
| `test/scripts/coding_agent_max_ctx_compact_lab.py` | API continuous multi-turn → max ctx |
| `test/scripts/context_max_ladder_lab.py` | Stepped single-prompt size ladder |
| `test/scripts/dsh_web_full_matrix.py` | Modes × efforts × short/coding |
