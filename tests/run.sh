#!/usr/bin/env bash

set -Eeuo pipefail

readonly TEST_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PROJECT_ROOT="$(cd -- "${TEST_DIR}/.." && pwd -P)"

cd "${PROJECT_ROOT}"

for script in scripts/*.sh tests/*.sh; do
  bash -n "${script}"
done

python3 -m compileall -q api

grep -Fq 'Qwen/Qwen3-0.6B' compose.yaml
grep -Fq '/v1/chat/completions' api/app.py
grep -Fq 'Authorization: Bearer' scripts/smoke_test.sh
grep -Fq 'cap_drop:' compose.yaml
grep -Fq 'no-new-privileges:true' compose.yaml

if grep -Eq '/var/run/docker.sock|hermes.*(volume|network)' compose.yaml; then
  printf 'Isolation check failed: prohibited Docker socket or Hermes attachment found.\n' >&2
  exit 1
fi

if rg -i --no-ignore 'AI_LAB|ai-lab|ai_lab|ai\.lab|AI[ -]lab' \
  --glob '!.git/**' --glob '!.agents/**' --glob '!.codex/**' \
  --glob '!tests/run.sh' .; then
  printf 'Naming check failed: legacy project identifiers remain.\n' >&2
  exit 1
fi

test_env="$(mktemp)"
trap 'rm -f -- "${test_env}"; find api -type d -name __pycache__ -prune -exec rm -rf {} +' EXIT
sed \
  -e 's|LLM_STUDIO_DATA_DIR=/opt/data/llm-studio|LLM_STUDIO_DATA_DIR=/tmp/llm-studio-test|' \
  -e 's|replace-with-at-least-32-random-characters|0123456789abcdef0123456789abcdef|' \
  .env.example >"${test_env}"

docker compose --project-name llm-studio-test --env-file "${test_env}" --file compose.yaml config --quiet

printf 'Static tests passed. No container was started and no model was downloaded.\n'
