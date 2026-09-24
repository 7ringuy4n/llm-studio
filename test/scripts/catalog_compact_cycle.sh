#!/usr/bin/env bash
# Cycle OpenCode + DSH Standard AUTO compact across catalog models.
# Skips models already proven unless FORCE_ALL=1.
# Between models: unload + ollama rm + drop_caches (Vast SSH).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPTS="$ROOT/test/scripts"
RESULTS="$ROOT/docs/perf-results"
SUMMARY="$RESULTS/catalog-compact-cycle.jsonl"
SSH_HOST="${VAST_SSH_HOST:-root@50.217.254.165}"
SSH_PORT="${VAST_SSH_PORT:-40820}"
DSH_URL_FILE="${DSH_URL_FILE:-/tmp/dsh_url.txt}"
SKIP_DONE="${SKIP_DONE:-1}"

mkdir -p "$RESULTS"
: > "$SUMMARY"

ssh_r() {
  ssh -o BatchMode=yes -o ConnectTimeout=15 -p "$SSH_PORT" "$SSH_HOST" "$@"
}

remote_cleanup() {
  local tags=("$@")
  ssh_r "bash -s" <<REMOTE
export OLLAMA_MODELS=/workspace/ollama/models
for t in ${tags[*]}; do
  curl -sS http://127.0.0.1:11434/api/generate -d "{\"model\":\"\$t\",\"keep_alive\":0}" >/dev/null 2>&1 || true
  ollama stop "\$t" 2>/dev/null || true
  ollama rm "\$t" 2>/dev/null || true
done
sync
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true
ollama list || true
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
df -h /workspace | tail -1
REMOTE
}

remote_ensure() {
  local base="$1" alias="$2" ctx="$3"
  ssh_r "bash -s" <<REMOTE
set -e
export OLLAMA_MODELS=/workspace/ollama/models
if ! ollama list | awk '{print \$1}' | grep -qx '$base'; then
  ollama pull '$base'
fi
if ! ollama list | awk '{print \$1}' | grep -qx '$alias'; then
  printf '%s\\n' 'FROM $base' 'PARAMETER num_ctx $ctx' > /tmp/Modelfile.lab
  ollama create '$alias' -f /tmp/Modelfile.lab
fi
ollama list | head -20
# warm
curl -sS -m 180 http://127.0.0.1:11434/api/generate -d '{"model":"$alias","prompt":"Reply ONLY: OK","stream":false,"options":{"num_predict":8}}' | head -c 200
echo
REMOTE
}

already_pass() {
  local agent="$1" key="$2"
  [[ "$SKIP_DONE" == "1" ]] || return 1
  if [[ "$agent" == "opencode" ]]; then
    case "$key" in
      Qwen/Qwen3.5-9B|Qwen/Qwen3.8-27B) return 0 ;;
    esac
  fi
  if [[ "$agent" == "dsh" && "$key" == "Qwen/Qwen3.5-9B" ]]; then
    return 0
  fi
  return 1
}

run_opencode() {
  local key="$1" alias="$2" ctx="$3" reserved="$4"
  local out="$RESULTS/opencode-compact-flood-$(echo "$key" | tr '/:' '__').jsonl"
  local lab="/tmp/opencode-lab-$(echo "$alias" | tr ':/' '__')"
  rm -rf "$lab"; mkdir -p "$lab"
  : > "$out"
  local chunk=$(( ctx / 50 )); [[ $chunk -lt 200 ]] && chunk=200; [[ $chunk -gt 800 ]] && chunk=800
  local turns=50
  [[ $ctx -le 32768 ]] && turns=40
  [[ $ctx -ge 65536 ]] && turns=55
  echo "=== OpenCode $key alias=$alias ctx=$ctx reserved=$reserved ==="
  set +e
  OPENCODE_TEST_DIR="$lab" \
  CATALOG_KEY="$key" \
  OPENCODE_MODEL="ollama/$alias" \
  OPENCODE_COMPACT_CHUNK_REPS="$chunk" \
  OPENCODE_COMPACT_MAX_TURNS="$turns" \
  OPENCODE_RESERVED="$reserved" \
  OPENCODE_OUTPUT_CAP=512 \
  RESULTS="$out" \
  # Override tag/ctx by patching env through a wrapper: flood reads catalog tag;
  # force via OPENCODE_MODEL and rewriting model_ctx temporarily is hard — instead
  # set CTX by exporting through a tiny wrapper.
  bash -c '
    set -euo pipefail
    SCRIPTS="'"$SCRIPTS"'"
    KEY="'"$key"'"
    ALIAS="'"$alias"'"
    CTX="'"$ctx"'"
    # monkey-patch: run flood but inject META
    export OPENCODE_TEST_DIR="'"$lab"'"
    export RESULTS="'"$out"'"
    export OPENCODE_MODEL="ollama/'"$alias"'"
    export OPENCODE_COMPACT_CHUNK_REPS="'"$chunk"'"
    export OPENCODE_COMPACT_MAX_TURNS="'"$turns"'"
    export OPENCODE_RESERVED="'"$reserved"'"
    export OPENCODE_OUTPUT_CAP=512
    # Write a one-shot flood using same script guts via env TAG/CTX override of model_ctx
    META=$(python3 -c "import json; print(json.dumps({\"ollama_tag\":\"'"$alias"'\",\"test_context_tokens\":'"$ctx"',\"chunk_reps\":'"$chunk"',\"max_turns\":'"$turns"'}))")
    export CATALOG_KEY="'"$key"'"
    # Temporarily shadow model_ctx.py output by wrapping
    TMPY=$(mktemp)
    cat > "$TMPY" <<PY
import json,sys
print(json.dumps({"id":"'"$key"'","alias":"lab","ollama_tag":"'"$alias"'","test_context_tokens":'"$ctx"',"catalog_context_tokens":'"$ctx"',"chunk_reps":'"$chunk"',"max_turns":'"$turns'"}))
PY
    # Run flood with PATH override: put fake model_ctx first
    mkdir -p /tmp/fake_model_ctx
    cp "$TMPY" /tmp/fake_model_ctx/model_ctx.py
    chmod +x /tmp/fake_model_ctx/model_ctx.py
    # Patch: call flood but replace SCRIPTS model_ctx — simplest: sed copy
    FLOOD=$(mktemp)
    sed "s|META=\$(python3 \"\$SCRIPTS/model_ctx.py\"|META=\$(python3 /tmp/fake_model_ctx/model_ctx.py|" \
      "$SCRIPTS/opencode_compact_flood.sh" > "$FLOOD"
    # Fix broken sed — use python rewrite
    python3 - <<P2
from pathlib import Path
src=Path("'"$SCRIPTS"'/opencode_compact_flood.sh").read_text()
src=src.replace(
  \'META=$(python3 "$SCRIPTS/model_ctx.py" "$CATALOG_KEY")\',
  \'META=$(python3 /tmp/fake_model_ctx/model_ctx.py)\'
)
Path("'"$FLOOD"'").write_text(src)
P2
    bash "$FLOOD"
    RC=$?
    rm -f "$TMPY" "$FLOOD"
    exit $RC
  '
  local rc=$?
  set -e

  # Session export proof (token-drop / compaction part)
  local sid
  sid=$(rg -o 'ses_[A-Za-z0-9]+' "$out" 2>/dev/null | head -1 || true)
  local pass=0 auto=false before="" after=""
  if [[ -n "$sid" ]]; then
    (cd "$lab" && opencode export "$sid" > "/tmp/oc-export-$alias.json" 2>/dev/null) || true
    python3 - <<PY
import json
from pathlib import Path
outp=Path("$RESULTS")
alias="$alias"
key="$key"
rows=[json.loads(l) for l in Path("$out").read_text().splitlines() if l.strip()] if Path("$out").exists() else []
drop=None
for i,r in enumerate(rows):
  if r.get("token_drop") or r.get("saw_auto_compact"):
    drop=r; break
  if i>0 and r.get("tokens_total") and rows[i-1].get("tokens_total") and r["tokens_total"]<rows[i-1]["tokens_total"]-15000:
    drop=r; drop["tokens_prev"]=rows[i-1]["tokens_total"]; break
exp=Path("/tmp/oc-export-$alias.json")
auto=False; evidence={}
if exp.exists() and exp.stat().st_size>10:
  data=json.loads(exp.read_text())
  for m in data.get("messages",[]):
    parts=m.get("parts") or []
    info=m.get("info") or {}
    for p in parts:
      if p.get("type")=="compaction" and p.get("auto") is True:
        auto=True
        evidence={"type":"compaction","auto":True,"overflow":p.get("overflow")}
    if info.get("mode")=="compaction":
      evidence["summary_finish"]=info.get("finish")
      evidence["summary_tokens"]=info.get("tokens")
pass_ok = bool(auto or (drop and drop.get("saw_auto_compact")))
proof={
  "kind":"opencode-auto-compact-proof",
  "catalog_key":key,
  "model":f"ollama/{alias}",
  "test_context_tokens":$ctx,
  "reserved":$reserved,
  "result":"PASS" if pass_ok else "FAIL",
  "evidence":evidence,
  "flood_drop":drop,
}
safe=alias.replace(":","_").replace("/","_")
outp.joinpath(f"opencode-auto-compact-proof-{safe}.json").write_text(json.dumps(proof,indent=2)+"\n")
print(json.dumps({"agent":"opencode","key":key,"result":proof["result"],"auto":auto,"drop":bool(drop)}))
Path("$SUMMARY").open("a").write(json.dumps({"agent":"opencode","catalog_key":key,"alias":alias,"ctx":$ctx,"result":proof["result"],"auto":auto})+"\n")
PY
  else
    echo "{\"agent\":\"opencode\",\"catalog_key\":\"$key\",\"result\":\"FAIL\",\"reason\":\"no_session\"}" | tee -a "$SUMMARY"
  fi
}

run_dsh() {
  local key="$1" alias="$2" ctx="$3"
  local out="$RESULTS/dsh-web-compact-flood-$(echo "$alias" | tr ':/' '__').jsonl"
  echo "=== DSH $key alias=$alias ctx=$ctx ==="
  # Point default model
  python3 - <<PY
from pathlib import Path
p=Path.home()/".dsh"/"settings.yaml"
t=p.read_text()
import re
t2=re.sub(r"(agent-default-model:\n  provider: vast\n  model: ).*", r"\1$alias", t)
# if no match multiline:
if "model: $alias" not in t2:
  t2=re.sub(r"(agent-default-model:\n  provider: vast\n  model: )[^\n]+", r"\1$alias", t, count=1)
p.write_text(t2)
print("default model -> $alias")
PY
  export DSH_WEB_URL="$(cat "$DSH_URL_FILE")"
  export DSH_COMPACT_CATALOG_KEY="$key"
  export DSH_COMPACT_MODEL="$alias"
  export DSH_COMPACT_CONTEXT_TOKENS="$ctx"
  export DSH_COMPACT_MODE=standard
  export DSH_COMPACT_MAX_TURNS=40
  export DSH_COMPACT_CHUNK_REPS=$(( ctx > 40000 ? 400 : 250 ))
  export DSH_COMPACT_FLOOD_CHARS=12000
  export RESULTS="$out"
  unset BSK_SESSION || true
  set +e
  # Shadow model_ctx for DSH flood similarly
  mkdir -p /tmp/fake_model_ctx
  python3 -c "import json; open('/tmp/fake_model_ctx/model_ctx.py','w').write('import json\\nprint(json.dumps({\"ollama_tag\":\"$alias\",\"test_context_tokens\":$ctx,\"chunk_reps\":300,\"max_turns\":40}))\\n')"
  FLOOD=$(mktemp)
  python3 - <<P2
from pathlib import Path
src=Path("$SCRIPTS/dsh_web_compact_flood.sh").read_text()
src=src.replace(
  'META=$(python3 "$SCRIPTS/model_ctx.py" "$CATALOG_KEY")',
  'META=$(python3 /tmp/fake_model_ctx/model_ctx.py)'
)
Path("$FLOOD").write_text(src)
P2
  timeout 2400 bash "$FLOOD"
  local rc=$?
  set -e
  rm -f "$FLOOD"

  python3 - <<PY
import json,glob,os,subprocess,re
from pathlib import Path
out=Path("$out")
rows=[json.loads(l) for l in out.read_text().splitlines() if l.strip()] if out.exists() else []
auto=any(r.get("saw_auto_compact") for r in rows)
detail=""
for r in rows:
  if r.get("saw_auto_compact"):
    detail=r.get("compact_detail") or ""
    break
# Also scan newest session
try:
  sessions=sorted(glob.glob(os.path.expanduser("~/.dsh/sessions/**/session.v3.jsonl.zstd"), recursive=True), key=os.path.getmtime, reverse=True)
  if sessions:
    raw=subprocess.check_output(["zstd","-dc",sessions[0]], stderr=subprocess.DEVNULL)
    for line in raw.splitlines():
      if not line.strip(): continue
      o=json.loads(line)
      if o.get("type")=="compaction/start":
        d=o.get("data") or {}
        if not d.get("sourceCommandId"):
          auto=True
          detail=f"auto_turn={d.get('turn')}"
except Exception as e:
  detail += f"|sess:{type(e).__name__}"
result="PASS" if auto else "FAIL"
proof={
  "kind":"dsh-auto-compact-proof",
  "catalog_key":"$key",
  "model":"$alias",
  "test_context_tokens":$ctx,
  "result":result,
  "compact_detail":detail,
  "flood_rows":len(rows),
}
safe="$alias".replace(":","_").replace("/","_")
Path("$RESULTS/dsh-auto-compact-proof-"+safe+".json").write_text(json.dumps(proof,indent=2)+"\n")
Path("$SUMMARY").open("a").write(json.dumps({"agent":"dsh","catalog_key":"$key","alias":"$alias","ctx":$ctx,"result":result,"detail":detail})+"\n")
print(json.dumps(proof))
PY
}

# Model matrix: catalog_key|base|alias|ctx|reserved
# Compact-lab windows: 262144 catalog defaults capped to 32k; 131072 long models to 64k for wall-clock.
MODELS=(
  "Qwen/Qwen3.8-27B|qwen3.8:27b|qwen3.8:27b-ctx64k|65536|16384"
  "Qwen/Qwen3.5-0.8B|qwen3.5:0.8b|qwen3.5:0.8b-ctx32k|32768|8192"
  "Qwen/Qwen3.5-2B|qwen3.5:2b|qwen3.5:2b-ctx32k|32768|8192"
  "Qwen/Qwen3-1.7B|qwen3:1.7b|qwen3:1.7b-ctx32k|32768|8192"
  "Qwen/Qwen3.5-4B|qwen3.5:4b|qwen3.5:4b-ctx32k|32768|8192"
  "Qwen/Qwen3-8B|qwen3:8b|qwen3:8b-ctx40k|40960|10240"
  "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B|deepseek-r1:7b|deepseek-r1:7b-ctx64k|65536|16384"
  "meta-llama/Llama-3.1-8B-Instruct|llama3.1:8b|llama3.1:8b-ctx64k|65536|16384"
)

AGENTS="${COMPACT_AGENTS:-dsh,opencode}"

for entry in "${MODELS[@]}"; do
  IFS='|' read -r key base alias ctx reserved <<<"$entry"
  echo "######## CYCLE $key ($alias ctx=$ctx) ########"

  need_dsh=0 need_oc=0
  if [[ "$AGENTS" == *dsh* ]] && ! already_pass dsh "$key"; then need_dsh=1; fi
  if [[ "$AGENTS" == *opencode* ]] && ! already_pass opencode "$key"; then need_oc=1; fi
  if [[ $need_dsh -eq 0 && $need_oc -eq 0 ]]; then
    echo "skip (already PASS) $key"
    continue
  fi

  # Ensure model present (don't rm current if already right)
  remote_ensure "$base" "$alias" "$ctx"

  if [[ $need_dsh -eq 1 ]]; then
    run_dsh "$key" "$alias" "$ctx" || echo "dsh_fail $key"
  fi
  if [[ $need_oc -eq 1 ]]; then
    run_opencode "$key" "$alias" "$ctx" "$reserved" || echo "oc_fail $key"
  fi

  # Cleanup this model before next (keep disk free)
  remote_cleanup "$alias" "$base"
done

echo "SUMMARY -> $SUMMARY"
cat "$SUMMARY"
