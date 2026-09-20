#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

umask 077

for command in awk curl docker free ip openssl python3 ss; do
  require_command "${command}"
done

docker compose version >/dev/null 2>&1 || die 'Docker Compose v2 is required'
docker info >/dev/null 2>&1 || die 'Docker daemon is unavailable or the current user lacks permission'

log 'Phase 1/6: recording the read-only environment inspection'
"${SCRIPT_DIR}/inspect_environment.sh" "${PROJECT_ROOT}/docs/environment.md"
if [[ "$(id -u)" == 0 && -n "${SUDO_UID:-}" ]]; then
  chown "${SUDO_UID}:${SUDO_GID}" -- "${PROJECT_ROOT}/docs/environment.md"
fi

log 'Phase 2/6: validating host resources and isolation constraints'
if [[ ! -r /etc/os-release ]]; then
  die '/etc/os-release is unavailable'
fi
# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != ubuntu ]]; then
  if [[ " ${ID_LIKE:-} " == *' ubuntu '* ]]; then
    log "WARNING: ${PRETTY_NAME:-${ID}} is Ubuntu-compatible but is not the primary tested target"
  else
    die "This setup supports Ubuntu and Ubuntu-compatible Linux; detected ${ID:-unknown}"
  fi
fi

memory_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
cpu_count="$(nproc)"
(( cpu_count >= 4 )) || log "WARNING: ${cpu_count} CPUs detected; the target is at least 4"
(( memory_kib >= 14 * 1024 * 1024 )) || log 'WARNING: less than approximately 14 GiB RAM detected; model loading may fail'

if docker ps -a --format '{{.Names}} {{.Image}} {{.Labels}}' | grep -qi hermes; then
  log 'Existing Hermes-related containers detected and recorded; they will not be changed.'
else
  log 'No Hermes marker was detected automatically; review docs/environment.md before production use.'
fi

if docker network inspect llm-studio-net >/dev/null 2>&1; then
  network_owner="$(docker network inspect --format '{{ index .Labels "llm.studio.owner" }}' llm-studio-net 2>/dev/null || true)"
  [[ "${network_owner}" == llm-studio ]] || die 'Network llm-studio-net already exists but is not owned by this project'
fi

if docker container inspect llm-studio-api >/dev/null 2>&1; then
  container_owner="$(docker container inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' llm-studio-api 2>/dev/null || true)"
  [[ "${container_owner}" == llm-studio ]] || die 'Container llm-studio-api already exists but is not owned by this project'
fi

bind_address="${LLM_STUDIO_BIND_ADDRESS:-$(env_value LLM_STUDIO_BIND_ADDRESS 127.0.0.1)}"
port="${LLM_STUDIO_PORT:-$(env_value LLM_STUDIO_PORT 18080)}"
data_dir="${LLM_STUDIO_DATA_DIR:-$(env_value LLM_STUDIO_DATA_DIR /opt/data/llm-studio)}"

assert_safe_bind_address "${bind_address}"
[[ "${port}" =~ ^[0-9]+$ ]] && (( port >= 1024 && port <= 65535 )) \
  || die 'LLM_STUDIO_PORT must be an integer from 1024 through 65535'

if [[ "${bind_address}" != 127.0.0.1 && "${bind_address}" != ::1 ]]; then
  ip addr show | grep -Fq "${bind_address}" \
    || die "Private bind address ${bind_address} is not assigned to this host"
fi

if ss -H -ltn | awk -v wanted_port="${port}" '$4 ~ (":" wanted_port "$") { found = 1 } END { exit(found ? 0 : 1) }'; then
  if ! docker ps --filter name='^/llm-studio-api$' --format '{{.Names}}' | grep -qx llm-studio-api; then
    die "TCP port ${port} is already in use"
  fi
fi

parent_dir="$(dirname -- "${data_dir}")"
if [[ ! -d "${parent_dir}" ]]; then
  mkdir -p -- "${parent_dir}" 2>/dev/null \
    || die "Cannot create ${parent_dir}; run with sufficient permission (usually sudo)"
fi
available_kib="$(df -Pk "${parent_dir}" | awk 'NR == 2 {print $4}')"
(( available_kib >= 10 * 1024 * 1024 )) \
  || die 'At least 10 GiB free disk is required before setup'

log 'Phase 3/6: creating isolated LLM Studio directories and configuration'
for directory in models datasets training checkpoints rag vectorstore documents api logs notebooks scripts configs experiments backups; do
  install -d -m 0750 -- "${data_dir}/${directory}"
done

api_key="${LLM_STUDIO_API_KEY:-$(env_value LLM_STUDIO_API_KEY '')}"
if [[ -z "${api_key}" || "${api_key}" == replace-with-* ]]; then
  api_key="$(openssl rand -hex 32)"
fi
(( ${#api_key} >= 32 )) || die 'LLM_STUDIO_API_KEY must contain at least 32 characters'
[[ "${api_key}" =~ ^[A-Za-z0-9._-]+$ ]] \
  || die 'LLM_STUDIO_API_KEY may contain only letters, numbers, dot, underscore, and hyphen'

if [[ "$(id -u)" == 0 ]]; then
  app_uid="${SUDO_UID:-10001}"
  app_gid="${SUDO_GID:-10001}"
  chown "${app_uid}:${app_gid}" -- "${data_dir}" "${data_dir}"/*
else
  app_uid="$(id -u)"
  app_gid="$(id -g)"
fi

env_tmp="$(mktemp "${PROJECT_ROOT}/.env.tmp.XXXXXX")"
trap 'rm -f -- "${env_tmp:-}"' EXIT
{
  printf 'LLM_STUDIO_BIND_ADDRESS=%s\n' "${bind_address}"
  printf 'LLM_STUDIO_PORT=%s\n' "${port}"
  printf 'LLM_STUDIO_DATA_DIR=%s\n' "${data_dir}"
  printf 'LLM_STUDIO_API_KEY=%s\n' "${api_key}"
  printf 'LLM_STUDIO_APP_UID=%s\n' "${app_uid}"
  printf 'LLM_STUDIO_APP_GID=%s\n' "${app_gid}"
  printf 'MODEL_ID=%s\n' "$(env_value MODEL_ID Qwen/Qwen3-0.6B)"
  printf 'MODEL_REVISION=%s\n' "$(env_value MODEL_REVISION main)"
  printf 'MODEL_MAX_INPUT_TOKENS=%s\n' "$(env_value MODEL_MAX_INPUT_TOKENS 2048)"
  printf 'MODEL_MAX_NEW_TOKENS=%s\n' "$(env_value MODEL_MAX_NEW_TOKENS 512)"
  printf 'MODEL_LOAD_ON_START=%s\n' "$(env_value MODEL_LOAD_ON_START false)"
  printf 'LLM_STUDIO_CPU_THREADS=%s\n' "$(env_value LLM_STUDIO_CPU_THREADS 3)"
  printf 'LLM_STUDIO_REQUEST_TIMEOUT_SECONDS=%s\n' "$(env_value LLM_STUDIO_REQUEST_TIMEOUT_SECONDS 180)"
  printf 'LLM_STUDIO_MAX_CONCURRENT_REQUESTS=%s\n' "$(env_value LLM_STUDIO_MAX_CONCURRENT_REQUESTS 1)"
  printf 'LLM_STUDIO_RATE_LIMIT_PER_MINUTE=%s\n' "$(env_value LLM_STUDIO_RATE_LIMIT_PER_MINUTE 30)"
} >"${env_tmp}"
chmod 0600 "${env_tmp}"
mv -f -- "${env_tmp}" "${ENV_FILE}"
if [[ "$(id -u)" == 0 && -n "${SUDO_UID:-}" ]]; then
  chown "${SUDO_UID}:${SUDO_GID}" -- "${ENV_FILE}"
fi
trap - EXIT

log 'Phase 4/6: validating the Docker Compose configuration'
compose config --quiet

if [[ "${LLM_STUDIO_SETUP_NO_START:-false}" == true ]]; then
  log 'LLM_STUDIO_SETUP_NO_START=true: validation complete; images and services were not started.'
  exit 0
fi

log 'Phase 5/6: building and starting only the llm-studio project'
compose build
compose up --detach

log 'Phase 6/6: waiting for health and running an authenticated smoke test'
deadline=$((SECONDS + 240))
until curl --silent --show-error --fail --max-time 3 "http://${bind_address}:${port}/health" >/dev/null; do
  if (( SECONDS >= deadline )); then
    compose ps >&2 || true
    compose logs --tail 80 api >&2 || true
    die 'API health check did not pass within 240 seconds'
  fi
  sleep 2
done

"${SCRIPT_DIR}/smoke_test.sh"

log 'Setup complete.'
printf 'Base URL: http://%s:%s/v1\n' "${bind_address}" "${port}"
printf 'API key: stored in %s (mode 0600; value not printed)\n' "${ENV_FILE}"
printf 'Model: %s (downloaded lazily on the first chat request)\n' "$(env_value MODEL_ID Qwen/Qwen3-0.6B)"
printf 'Environment report: %s\n' "${PROJECT_ROOT}/docs/environment.md"
