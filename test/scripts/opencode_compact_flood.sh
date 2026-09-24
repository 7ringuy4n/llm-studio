#!/usr/bin/env bash
# OpenCode AUTO compact flood — same session via --continue (required for growth).
# Per-model ctx from CATALOG_KEY. Never sends /compact.
set -euo pipefail
ROOT="${OPENCODE_TEST_DIR:-/tmp/opencode-compact-lab}"
OUT="${RESULTS:-/home/tringuyen/Documents/llm-studio/docs/perf-results/opencode-compact-flood.jsonl}"
CATALOG_KEY="${CATALOG_KEY:-Qwen/Qwen3.5-9B}"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

META=$(python3 "$SCRIPTS/model_ctx.py" "$CATALOG_KEY")
TAG="${OPENCODE_TAG:-$(python3 -c "import json,sys; print(json.load(sys.stdin)['ollama_tag'])" <<<"$META")}"
CTX="${OPENCODE_CTX:-$(python3 -c "import json,sys; print(json.load(sys.stdin)['test_context_tokens'])" <<<"$META")}"
MAX_TURNS="${OPENCODE_COMPACT_MAX_TURNS:-$(python3 -c "import json,sys; print(json.load(sys.stdin)['max_turns'])" <<<"$META")}"
CHUNK_REPS="${OPENCODE_COMPACT_CHUNK_REPS:-$(python3 -c "import json,sys; print(json.load(sys.stdin)['chunk_reps'])" <<<"$META")}"
MODEL="${OPENCODE_MODEL:-ollama/$TAG}"
OUT_CAP="${OPENCODE_OUTPUT_CAP:-256}"

mkdir -p "$ROOT" "$(dirname "$OUT")"
: > "$OUT"
cd "$ROOT"

TAG="$TAG" CTX="$CTX" OUT_CAP="$OUT_CAP" MODEL="$MODEL" OPENCODE_RESERVED="${OPENCODE_RESERVED:-}" python3 - <<'PY'
import json, os
from pathlib import Path
p = Path.home() / ".config" / "opencode" / "opencode.json"
cfg = json.loads(p.read_text()) if p.exists() else {}
tag, ctx, out_cap, model = os.environ["TAG"], int(os.environ["CTX"]), int(os.environ["OUT_CAP"]), os.environ["MODEL"]
cfg["model"] = model
cfg["small_model"] = model
cfg.setdefault("provider", {}).setdefault("ollama", {}).setdefault("models", {})
cfg["provider"]["ollama"]["npm"] = "@ai-sdk/openai-compatible"
cfg["provider"]["ollama"]["name"] = "Ollama (Vast tunnel)"
cfg["provider"]["ollama"]["options"] = {"baseURL": "http://127.0.0.1:11434/v1"}
cfg["provider"]["ollama"]["models"][tag] = {
    "name": f"{tag} (per-model max ctx={ctx})",
    # limit.input required for compaction.reserved to apply (else reserved is ignored)
    "limit": {"context": ctx, "input": ctx, "output": out_cap},
}
env_r = os.environ.get("OPENCODE_RESERVED", "").strip()
reserved = int(env_r) if env_r else max(2048, min(32768, ctx // 4))
preserve = max(1024, min(8192, ctx // 16))
cfg["compaction"] = {
    "auto": True,
    "prune": True,
    "reserved": reserved,
    "preserve_recent_tokens": preserve,
}
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"updated {p} model={model} ctx={ctx} reserved={reserved}")
PY

CHUNK=$(python3 -c "print(('ops-note ')*$CHUNK_REPS)")
compacted=0
for turn in $(seq 1 "$MAX_TURNS"); do
  echo "running test case ${turn}/${MAX_TURNS}: opencode/auto-compact/${TAG}/turn-${turn} ctx=${CTX}"
  MSG=$(TURN=$turn CHUNK="$CHUNK" python3 -c "
import os
t=int(os.environ['TURN']); c=os.environ['CHUNK']
print(f'[opencode auto-compact turn={t}] Reply ONLY: ACK{t}. No tools. Filler:\\n{c}'[:20000])
")
  set +e
  if [[ $turn -eq 1 ]]; then
    OUT_TXT=$(opencode run --model "$MODEL" --format json --auto "$MSG" 2>&1)
  else
    OUT_TXT=$(opencode run --continue --model "$MODEL" --format json --auto "$MSG" 2>&1)
  fi
  RC=$?
  set -e
  printf '%s' "$OUT_TXT" > /tmp/opencode_turn_out.txt
  python3 - <<PY
import json, re
from pathlib import Path
text = Path("/tmp/opencode_turn_out.txt").read_text(errors="replace")
auto = bool(re.search(
    r'"type"\s*:\s*"[^"]*compact[^"]*"|"mode"\s*:\s*"compaction"|compacting|compacted|SessionCompaction|"auto"\s*:\s*true',
    text,
    re.I,
))
# avoid false positive on user asking to summarize
if re.search(r'like me to summarize|please summarize|summarize\?', text, re.I) and not re.search(r'compaction|compacted|"type"\s*:\s*"compaction"', text, re.I):
    auto = False
toks = re.findall(r'"total"\s*:\s*(\d+)', text)
last_total = int(toks[-1]) if toks else None
prev_total = None
try:
    prev_lines = Path("$OUT").read_text().splitlines()
    if prev_lines:
        prev_total = json.loads(prev_lines[-1]).get("tokens_total")
except Exception:
    prev_total = None
token_drop = bool(prev_total and last_total is not None and last_total < prev_total - 7000)
if token_drop:
    auto = True
row = {
  "turn": $turn,
  "m": $MAX_TURNS,
  "kind": "opencode-auto-compact-flood",
  "catalog_key": "$CATALOG_KEY",
  "model": "$MODEL",
  "test_context_tokens": $CTX,
  "rc": $RC,
  "saw_auto_compact": auto,
  "token_drop": token_drop,
  "tokens_total": last_total,
  "tokens_prev": prev_total,
  "saw_overflow": bool(re.search(r"context overflow|maximum context|too long", text, re.I)),
  "preview": text[-500:].replace("\n", " ")[:350],
}
Path("$OUT").open("a").write(json.dumps(row, ensure_ascii=False) + "\n")
print(json.dumps({k: row[k] for k in ("turn", "saw_auto_compact", "token_drop", "saw_overflow", "rc", "tokens_total", "tokens_prev")}))
if row["saw_auto_compact"]:
  raise SystemExit(10)
PY
  code=$?
  if [[ $code -eq 10 ]]; then
    echo "AUTO_COMPACT_DETECTED at turn $turn"
    compacted=1
    set +e
    OUT_TXT=$(opencode run --continue --model "$MODEL" --format json --auto "Post-auto-compact: reply ONLY ACK_PC" 2>&1)
    set -e
    printf '%s' "$OUT_TXT" > /tmp/opencode_turn_out.txt
    python3 - <<PY
import json, re
from pathlib import Path
text = Path("/tmp/opencode_turn_out.txt").read_text(errors="replace")
row = {
  "turn": "post-compact",
  "kind": "opencode-auto-compact-continue",
  "ok": bool(re.search(r"ACK_PC", text)),
  "preview": text[-300:].replace("\n", " ")[:250],
}
Path("$OUT").open("a").write(json.dumps(row, ensure_ascii=False) + "\n")
print(json.dumps(row))
PY
    break
  fi
done
echo "{\"wrote\":\"$OUT\",\"auto_compacted\":$compacted,\"turns\":$MAX_TURNS,\"model\":\"$MODEL\",\"test_context_tokens\":$CTX}"
