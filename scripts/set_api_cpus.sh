#!/usr/bin/env bash
# Apply API CPU budget on the VPS host (3 or 4) and recreate the API container.
# Usage: ./scripts/set_api_cpus.sh 3|4
set -euo pipefail
cpus="${1:?usage: $0 3|4}"
case "$cpus" in
  3|4) ;;
  *) echo "cpus must be 3 or 4" >&2; exit 2 ;;
esac
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
touch .env
python3 - "$cpus" <<'PY'
import re, sys
from pathlib import Path
cpus = sys.argv[1]
path = Path(".env")
text = path.read_text() if path.exists() else ""
def upsert(key: str, value: str, blob: str) -> str:
    line = f"{key}={value}"
    if re.search(rf"(?m)^{re.escape(key)}=", blob):
        return re.sub(rf"(?m)^{re.escape(key)}=.*$", line, blob)
    return blob.rstrip() + ("\n" if blob and not blob.endswith("\n") else "") + line + "\n"
text = upsert("LLM_STUDIO_API_CPUS", f"{cpus}.0", text)
text = upsert("LLM_STUDIO_CPU_THREADS", cpus, text)
path.write_text(text)
print(f"set LLM_STUDIO_API_CPUS={cpus}.0 LLM_STUDIO_CPU_THREADS={cpus}")
PY
# Recreate so cpus + env apply
source scripts/common.sh
assert_env_file
compose up -d --force-recreate --no-deps api
echo "waiting for health..."
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 || \
     curl -fsS "http://${LLM_STUDIO_BIND_ADDRESS:-10.8.0.1}:${LLM_STUDIO_PORT:-18080}/health" >/dev/null 2>&1; then
    echo "api healthy"
    docker inspect llm-studio-api --format 'NanoCPUs={{.HostConfig.NanoCpus}}'
    docker exec llm-studio-api sh -c 'printf "CPU_THREADS=%s N_BATCH=%s\n" "$LLM_STUDIO_CPU_THREADS" "$MODEL_GGUF_N_BATCH"'
    exit 0
  fi
  sleep 2
done
echo "api did not become healthy" >&2
exit 1
