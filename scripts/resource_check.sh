#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

printf 'CPU and load\n'
printf '------------\n'
nproc
uptime

printf '\nMemory\n------\n'
free -h

printf '\nDisk\n----\n'
if [[ -f "${ENV_FILE}" ]]; then
  df -h "$(env_value LLM_STUDIO_DATA_DIR /opt/data/llm-studio)"
else
  df -h "${PROJECT_ROOT}"
fi

printf '\nLLM Studio services\n---------------\n'
if [[ -f "${ENV_FILE}" ]]; then
  compose ps
  docker stats --no-stream llm-studio-api 2>/dev/null || true
else
  printf 'Not configured. Run scripts/setup.sh first.\n'
fi

