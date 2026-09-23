#!/usr/bin/env bash
# Full offline suite: static gate + focused units (host or API container).

set -Eeuo pipefail

readonly TEST_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PROJECT_ROOT="$(cd -- "${TEST_DIR}/.." && pwd -P)"

cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

UNITS=(
  "test/scripts/gguf_runtime_unit.py|gguf_runtime_unit"
  "test/scripts/model_management_unit.py|model_management_unit"
  "test/scripts/tool_calling_unit.py|tool_calling_unit"
  "test/scripts/tracing_unit.py|tracing_unit"
)

case_total=$((1 + ${#UNITS[@]}))
case_n=0
failed=0

_run_unit() {
  local path="$1"
  if python3 -c 'import fastapi, torch' >/dev/null 2>&1; then
    python3 "${path}"
    return
  fi
  if docker compose ps --status running --services 2>/dev/null | grep -qx api; then
    docker compose exec -T api python3 "/app/${path}" 2>/dev/null \
      || docker compose exec -T api python3 -c "
import runpy, sys
sys.path.insert(0, '/app')
runpy.run_path('${path}', run_name='__main__')
"
    return
  fi
  printf 'SKIP (no host fastapi/torch and no running api container): %s\n' "${path}" >&2
  return 0
}

case_n=$((case_n + 1))
printf 'running test case %s/%s: static_gate\n' "${case_n}" "${case_total}"
if ! bash "${TEST_DIR}/run.sh"; then
  printf 'FAIL: static_gate\n' >&2
  failed=$((failed + 1))
fi

for entry in "${UNITS[@]}"; do
  path="${entry%%|*}"
  name="${entry##*|}"
  case_n=$((case_n + 1))
  printf 'running test case %s/%s: %s\n' "${case_n}" "${case_total}" "${name}"
  if ! _run_unit "${path}"; then
    printf 'FAIL: %s\n' "${name}" >&2
    failed=$((failed + 1))
  fi
done

if (( failed > 0 )); then
  printf 'Offline suite FAILED: %s failing of %s\n' "${failed}" "${case_total}" >&2
  exit 1
fi

printf 'Offline suite PASS: %s/%s\n' "${case_total}" "${case_total}"
