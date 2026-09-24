#!/usr/bin/env bash
# DSH web Standard-mode continuous max-context flood (coding-agent style).
# See rule/DSH_COMPACT_FLOOD.md
export BSK_AUTO_START=0
export BSK_HOME="${BSK_HOME:-$HOME/.bsk}"
SID="${BSK_SESSION:-}"
RESULTS="${RESULTS:-/home/tringuyen/Documents/llm-studio/docs/perf-results/dsh-web-compact-flood.jsonl}"
MODE="${DSH_COMPACT_MODE:-standard}"
CATALOG_KEY="${DSH_COMPACT_CATALOG_KEY:-}"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"

# Per-model max ctx — never a shared 4k/8k suite
if [[ -n "$CATALOG_KEY" ]]; then
  META=$(python3 "$SCRIPTS/model_ctx.py" "$CATALOG_KEY")
  CTX=$(python3 -c "import json,sys; print(json.load(sys.stdin)['test_context_tokens'])" <<<"$META")
  DEFAULT_MODEL=$(python3 -c "import json,sys; m=json.load(sys.stdin); print(m['ollama_tag'])" <<<"$META")
  DEFAULT_TURNS=$(python3 -c "import json,sys; print(json.load(sys.stdin)['max_turns'])" <<<"$META")
  DEFAULT_CHUNK=$(python3 -c "import json,sys; print(json.load(sys.stdin)['chunk_reps'])" <<<"$META")
else
  CTX="${DSH_COMPACT_CONTEXT_TOKENS:-}"
  DEFAULT_MODEL=""
  DEFAULT_TURNS=60
  DEFAULT_CHUNK=120
fi

MODEL_LABEL="${DSH_COMPACT_MODEL:-$DEFAULT_MODEL}"
MAX_TURNS="${DSH_COMPACT_MAX_TURNS:-$DEFAULT_TURNS}"
CHUNK_REPS="${DSH_COMPACT_CHUNK_REPS:-$DEFAULT_CHUNK}"
CONTINUE_AFTER="${DSH_COMPACT_CONTINUE_AFTER:-5}"
KIND="${DSH_COMPACT_KIND:-coding-agent}"

if [[ -z "$MODEL_LABEL" ]]; then
  echo "Set DSH_COMPACT_CATALOG_KEY (preferred) or DSH_COMPACT_MODEL" >&2
  exit 1
fi
echo "dsh compact flood: model=$MODEL_LABEL catalog=${CATALOG_KEY:-n/a} ctx=${CTX:-from-DSH-settings} turns=$MAX_TURNS chunk_reps=$CHUNK_REPS"

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
  local url="${DSH_WEB_URL:-}"
  if [[ -z "$url" && -f /tmp/dsh_url.txt ]]; then
    url=$(cat /tmp/dsh_url.txt)
  fi
  if [[ -z "$url" ]]; then
    url="http://127.0.0.1:8080"
  fi
  bsk navigate "$url" --session "$SID" >/dev/null || true
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
    box=$(ref_of '@(e\d+) textbox "(?:Describe what you want|Message or run a task)')
    [[ -n "$box" ]] || box=$(ref_of '@(e\d+) textbox "Message')
    [[ -n "$box" ]] || box=$(ref_of '@(e\d+) textbox "Describe')
    [[ -n "$box" ]] || { sleep 1; continue; }
    if bsk fill "@$box" --value "$msg" --session "$SID" >/tmp/dsh_fill.err 2>&1; then
      break
    fi
    # Always prefer evaluate for large payloads (bsk fill truncates / loses focus)
    MSG_JSON=$(MSG="$msg" python3 -c "import json,os; print(json.dumps(os.environ['MSG']))")
    if bsk evaluate --session "$SID" "(function(){const el=document.querySelector('textarea,[contenteditable=true],[role=textbox]');if(!el)return 'noel';const v=$MSG_JSON;el.focus();if(el.tagName==='TEXTAREA'||el.tagName==='INPUT'){el.value=v;}else{el.textContent=v;}el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return 'ok:'+String(el.value||el.textContent||'').length;})()" >/tmp/dsh_fill.err 2>&1; then
      break
    fi
    sleep 1
  done
  # If fill reported ok but message is huge, force evaluate anyway
  if [[ ${#msg} -gt 3500 ]]; then
    MSG_JSON=$(MSG="$msg" python3 -c "import json,os; print(json.dumps(os.environ['MSG']))")
    bsk evaluate --session "$SID" "(function(){const el=document.querySelector('textarea,[contenteditable=true],[role=textbox]');if(!el)return 'noel';const v=$MSG_JSON;el.focus();if(el.tagName==='TEXTAREA'||el.tagName==='INPUT'){el.value=v;}else{el.textContent=v;}el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));return 'ok:'+String(el.value||el.textContent||'').length;})()" >/tmp/dsh_fill.err 2>&1 || true
  fi
  sleep 0.4
  obs
  send=$(ref_of '@(e\d+) button "Send message"')
  if [[ -z "$send" ]]; then
    echo '{"wait_s":0,"saw_compact":false,"saw_auto_compact":false,"saw_overflow":false,"saw_error":true,"preview":"no-send"}'
    return 0
  fi
  bsk click "@$send" --session "$SID" >/dev/null
  local i=0
  while [[ $i -lt $timeout ]]; do
    sleep 3
    i=$((i+3))
    obs
    if grep -qiE 'Context compaction|compacted the conversation|Compacting context|Compacted [0-9]+ history items|could not produce a useful summary|CONTEXT_WINDOW_EXCEEDED' /tmp/dsh_compact_obs.txt; then
      break
    fi
    if grep -qiE 'Output token limit reached|CONTEXT_WINDOW' /tmp/dsh_compact_obs.txt; then
      break
    fi
    if grep -q 'textbox .*\[empty\]' /tmp/dsh_compact_obs.txt && ! grep -qiE 'Stop generation|Generating\.\.\.|Deep diving' /tmp/dsh_compact_obs.txt; then
      break
    fi
  done
  # Classify AUTO vs manual from newest session log (manual has sourceCommandId)
  python3 -c "
import json,re,glob,os,subprocess
from pathlib import Path
t=open('/tmp/dsh_compact_obs.txt').read()
ui=bool(re.search(r'Context compaction|compacted the conversation|Compacting context|Compacted \d+ history items', t, re.I))
auto=False; manual=False; detail=''
try:
  sessions=sorted(glob.glob(os.path.expanduser('~/.dsh/sessions/**/session.v3.jsonl.zstd'), recursive=True), key=os.path.getmtime, reverse=True)
  if sessions:
    raw=subprocess.check_output(['zstd','-dc',sessions[0]], stderr=subprocess.DEVNULL)
    if raw.strip():
      Path('/tmp/dsh_flood_sess.jsonl').write_bytes(raw)
      for line in open('/tmp/dsh_flood_sess.jsonl'):
        line=line.strip()
        if not line: continue
        o=json.loads(line)
        if o.get('type')=='compaction/start':
          d=o.get('data') or {}
          if d.get('sourceCommandId'):
            manual=True; detail='manual:'+str(d.get('sourceCommandId'))
          else:
            auto=True; detail='auto_turn='+str(d.get('turn'))
        if o.get('type')=='compaction/end' and (o.get('data') or {}).get('error'):
          detail += '|err='+str(o['data']['error'])[:120]
except Exception as e:
  detail='sess_parse:'+type(e).__name__
# UI Compacting without prior /compact in this flood => treat as auto candidate
if ui and not manual:
  auto=True
  if not detail: detail='ui_auto'
print(json.dumps({
  'wait_s': $i,
  'saw_compact': ui or auto,
  'saw_auto_compact': bool(auto) and not manual,
  'saw_manual_compact': manual,
  'compact_detail': detail,
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
# Large per-turn body so pressure reaches threshold inside per-model max ctx
# (bsk fill is tiny; evaluate injects a multi-kB payload).
FLOOD_CHARS="${DSH_COMPACT_FLOOD_CHARS:-12000}"
compacted=0
overflow=0
continue_left=0
phase=grow
for turn in $(seq 1 "$MAX_TURNS"); do
  echo "running test case ${turn}/${MAX_TURNS}: dsh-web/coding-max-ctx/${MODE}/turn-${turn} phase=${phase}"
  msg=$(TURN="$turn" CHUNK="$CHUNK" KIND="$KIND" PHASE="$phase" FLOOD_CHARS="$FLOOD_CHARS" python3 -c "
import os
turn=int(os.environ['TURN'])
chunk=os.environ['CHUNK']
phase=os.environ.get('PHASE','grow')
limit=int(os.environ.get('FLOOD_CHARS','12000'))
# Repeat chunk to fill budget (auto-compact pressure, not /compact)
pad = (chunk * ((limit // max(len(chunk),1)) + 1))[:limit]
body = (
    f'[auto-compact-flood turn={turn} phase={phase}] '
    f'Reply with exactly: ACK{turn}. No tools. Ignore filler.\\n{pad}'
)
print(body)
")
  out=$(send_wait "$msg" 360)
  echo "$out" | TURN="$turn" MAX="$MAX_TURNS" MODE="$MODE" MODEL="$MODEL_LABEL" PHASE="$phase" KIND="$KIND" python3 -c "
import json,sys,os
row=json.load(sys.stdin)
row.update({
  'n': int(os.environ['TURN']),
  'm': int(os.environ['MAX']),
  'mode': os.environ['MODE'],
  'model': os.environ['MODEL'],
  'turn': int(os.environ['TURN']),
  'kind': os.environ['KIND'],
  'phase': os.environ['PHASE'],
})
print(json.dumps(row, ensure_ascii=False))
" | tee -a "$RESULTS"

  if echo "$out" | grep -q '"saw_auto_compact": true'; then
    echo "AUTO_COMPACT_DETECTED at turn $turn — continuing ${CONTINUE_AFTER} turns to verify session still usable"
    compacted=1
    phase=post-compact
    continue_left=$CONTINUE_AFTER
    if [[ "$CONTINUE_AFTER" -le 0 ]]; then
      break
    fi
    continue
  fi
  # Manual /compact must NOT count as PASS for this lab
  if echo "$out" | grep -q '"saw_manual_compact": true'; then
    echo "MANUAL_COMPACT_IGNORED at turn $turn (lab requires auto)"
  fi
  if echo "$out" | grep -q '"saw_overflow": true'; then
    echo "OVERFLOW at turn $turn"
    overflow=1
    break
  fi
  if echo "$out" | grep -q '"saw_error": true'; then
    echo "ERROR at turn $turn"
    break
  fi
  if [[ "$phase" == "post-compact" ]]; then
    continue_left=$((continue_left - 1))
    if [[ "$continue_left" -le 0 ]]; then
      echo "POST_COMPACT_CONTINUE_DONE"
      break
    fi
  fi
done

RESULTS="$RESULTS" COMPACTED="$compacted" OVERFLOW="$overflow" python3 -c "
import json,os
from pathlib import Path
rows=[json.loads(l) for l in Path(os.environ['RESULTS']).read_text().splitlines() if l.strip()]
post=[r for r in rows if r.get('phase')=='post-compact']
auto_hits=[r for r in rows if r.get('saw_auto_compact')]
manual_hits=[r for r in rows if r.get('saw_manual_compact')]
post_ok=all(not r.get('saw_error') and not r.get('saw_overflow') for r in post) if post else None
print(json.dumps({
  'wrote': os.environ['RESULTS'],
  'turns': len(rows),
  'auto_compacted': os.environ['COMPACTED']=='1',
  'manual_compact_seen': bool(manual_hits),
  'overflow': os.environ['OVERFLOW']=='1',
  'post_compact_turns': len(post),
  'post_compact_continue_ok': post_ok,
  'outcome': (
    'auto_compact_and_continue' if os.environ['COMPACTED']=='1' and post_ok
    else 'auto_compact_only' if os.environ['COMPACTED']=='1'
    else 'manual_only_not_pass' if manual_hits and os.environ['COMPACTED']!='1'
    else 'overflow_no_compact' if os.environ['OVERFLOW']=='1'
    else 'continue_no_auto_compact' if rows and not any(r.get('saw_error') for r in rows)
    else 'error_or_inconclusive'
  ),
}, indent=2))
"
echo "BSK_SESSION=$SID"
