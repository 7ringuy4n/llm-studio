#!/usr/bin/env bash
# DSH web Standard-mode continuous compact flood (homelab).
# See rule/DSH_COMPACT_FLOOD.md
export BSK_AUTO_START=0
export BSK_HOME="${BSK_HOME:-$HOME/.bsk}"
SID="${BSK_SESSION:-}"
RESULTS="${RESULTS:-/home/tringuyen/Documents/llm-studio/docs/perf-results/dsh-web-compact-flood.jsonl}"
MODE="${DSH_COMPACT_MODE:-standard}"
MODEL_LABEL="${DSH_COMPACT_MODEL:-Qwen/Qwen3.5-0.8B}"
MAX_TURNS="${DSH_COMPACT_MAX_TURNS:-30}"
CHUNK_REPS="${DSH_COMPACT_CHUNK_REPS:-100}"

mkdir -p "$(dirname "$RESULTS")"
: > "$RESULTS"

obs() { bsk observe --session "$SID" 2>&1 > /tmp/dsh_compact_obs.txt; }

ref_of() {
  python3 -c "
import re,sys
pat=sys.argv[1]
t=open('/tmp/dsh_compact_obs.txt').read()
m=re.search(pat,t)
print(m.group(1) if m else '')
" "$1"
}

ensure_session() {
  if [[ -z "$SID" ]]; then
    SID=$(bsk session start --json --no-focus 2>&1 | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
  fi
  bsk navigate "http://127.0.0.1:8080" --session "$SID" >/dev/null || true
  sleep 1.5
}

new_session() {
  bsk press Escape --session "$SID" >/dev/null 2>&1 || true
  obs
  btn=$(ref_of '@(e\d+) button "New session"')
  [[ -n "$btn" ]] && bsk click "@$btn" --session "$SID" >/dev/null
  sleep 1.2
}

set_mode() {
  local want=$1
  bsk press Escape --session "$SID" >/dev/null 2>&1 || true
  obs
  btn=$(ref_of '@(e\d+) button "(?:Minimal|Standard|PTC|Creator) mode')
  [[ -n "$btn" ]] || return 1
  bsk click "@$btn" --session "$SID" >/dev/null
  sleep 0.7
  obs
  case "$want" in
    standard) pat='@(e\d+) menuitem "Standard mode' ;;
    minimal) pat='@(e\d+) menuitem "Minimal mode ' ;;
    minimal-web) pat='@(e\d+) menuitem "Minimal \+ Web' ;;
  esac
  ref=$(ref_of "$pat")
  [[ -n "$ref" ]] || return 1
  bsk click "@$ref" --session "$SID" >/dev/null
  sleep 1.2
}

select_model() {
  local label=$1
  bsk press Escape --session "$SID" >/dev/null 2>&1 || true
  obs
  btn=$(ref_of '@(e\d+) button "Select model')
  [[ -n "$btn" ]] || return 1
  bsk click "@$btn" --session "$SID" >/dev/null
  sleep 0.6
  obs
  if grep -q 'menuitem "Model ' /tmp/dsh_compact_obs.txt; then
    mref=$(ref_of '@(e\d+) menuitem "Model ')
    [[ -n "$mref" ]] && bsk click "@$mref" --session "$SID" >/dev/null && sleep 0.6 && obs
  fi
  ref=$(python3 -c "
import re,sys
label=sys.argv[1]
t=open('/tmp/dsh_compact_obs.txt').read()
for pat in [rf'@(e\d+) menuitemradio \"{re.escape(label)}\"', rf'@(e\d+) menuitemradio \"[^\"]*{re.escape(label)}[^\"]*\"']:
  m=re.search(pat,t)
  if m:
    print(m.group(1)); break
" "$label")
  [[ -n "$ref" ]] || return 1
  bsk click "@$ref" --session "$SID" >/dev/null
  sleep 0.8
  bsk press Escape --session "$SID" >/dev/null 2>&1 || true
}

send_wait() {
  local msg=$1 timeout=${2:-300}
  local attempt=0
  while [[ $attempt -lt 3 ]]; do
    attempt=$((attempt+1))
    obs
    box=$(ref_of '@(e\d+) textbox "Describe what you want')
    [[ -n "$box" ]] || { sleep 1; continue; }
    if bsk fill "@$box" --value "$msg" --session "$SID" >/tmp/dsh_fill.err 2>&1; then
      break
    fi
    sleep 1
  done
  sleep 0.4
  obs
  send=$(ref_of '@(e\d+) button "Send message"')
  if [[ -z "$send" ]]; then
    echo '{"wait_s":0,"saw_compact":false,"saw_overflow":false,"saw_error":true,"preview":"no-send"}'
    return 0
  fi
  bsk click "@$send" --session "$SID" >/dev/null
  local i=0
  while [[ $i -lt $timeout ]]; do
    sleep 3
    i=$((i+3))
    obs
    if grep -qiE 'Context compaction|compacted the conversation|Compacting context|could not produce a useful summary|CONTEXT_WINDOW_EXCEEDED' /tmp/dsh_compact_obs.txt; then
      break
    fi
    if grep -q 'textbox .*\[empty\]' /tmp/dsh_compact_obs.txt && ! grep -qiE 'Stop generation|Generating|Thinking' /tmp/dsh_compact_obs.txt; then
      break
    fi
  done
  python3 -c "
import json,re
t=open('/tmp/dsh_compact_obs.txt').read()
print(json.dumps({
  'wait_s': $i,
  'saw_compact': bool(re.search(r'Context compaction|compacted the conversation|Compacting context', t, re.I)),
  'saw_overflow': bool(re.search(r'CONTEXT_WINDOW|exceeded|could not produce a useful summary', t, re.I)),
  'saw_error': bool(re.search(r'Request failed', t, re.I)),
  'preview': ' | '.join(re.findall(r'StaticText \"([^\"]{0,100})\"', t)[-8:]),
}))
"
}

ensure_session
echo "SID=$SID"
new_session
set_mode "$MODE" || echo "mode_warn"
select_model "$MODEL_LABEL" || select_model "Qwen3.5 2B" || echo "model_warn"

CHUNK=$(N="$CHUNK_REPS" python3 -c "import os; print(('ops-note ')*int(os.environ['N']))")
compacted=0
for turn in $(seq 1 "$MAX_TURNS"); do
  echo "running test case ${turn}/${MAX_TURNS}: dsh-web/compact-flood/${MODE}/turn-${turn}"
  msg=$(TURN="$turn" CHUNK="$CHUNK" python3 -c "
import os
turn=int(os.environ['TURN'])
chunk=os.environ['CHUNK']
print(('COMPACT_FLOOD turn=%s. Reply ACK%s only. Filler:\n%s' % (turn, turn, chunk))[:3500])
")
  out=$(send_wait "$msg" 360)
  echo "$out" | TURN="$turn" MAX="$MAX_TURNS" MODE="$MODE" MODEL="$MODEL_LABEL" python3 -c "
import json,sys,os
row=json.load(sys.stdin)
row.update({
  'n': int(os.environ['TURN']),
  'm': int(os.environ['MAX']),
  'mode': os.environ['MODE'],
  'model': os.environ['MODEL'],
  'turn': int(os.environ['TURN']),
  'kind': 'compact-flood',
})
print(json.dumps(row, ensure_ascii=False))
" | tee -a "$RESULTS"
  if echo "$out" | grep -q '"saw_compact": true'; then
    echo "COMPACT_DETECTED at turn $turn"
    compacted=1
    break
  fi
  if echo "$out" | grep -q '"saw_overflow": true'; then
    echo "OVERFLOW at turn $turn"
    break
  fi
done

RESULTS="$RESULTS" COMPACTED="$compacted" python3 -c "
import json,os
from pathlib import Path
rows=[json.loads(l) for l in Path(os.environ['RESULTS']).read_text().splitlines() if l.strip()]
print(json.dumps({'wrote':os.environ['RESULTS'],'turns':len(rows),'compacted':os.environ['COMPACTED']=='1'}, indent=2))
"
echo "BSK_SESSION=$SID"
