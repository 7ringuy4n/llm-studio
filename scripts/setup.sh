#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"

umask 077

for command in awk curl free ip openssl python3 ss; do
  require_command "${command}"
done

command -v docker >/dev/null 2>&1 \
  || die 'Docker is not installed; run sudo ./scripts/install_docker.sh, then reconnect your shell'

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

for proxy_container in llm-studio-traefik-local llm-studio-traefik-internet llm-studio-openobserve llm-studio-otel-collector; do
  if docker container inspect "${proxy_container}" >/dev/null 2>&1; then
    container_owner="$(docker container inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "${proxy_container}" 2>/dev/null || true)"
    [[ "${container_owner}" == llm-studio ]] \
      || die "Container ${proxy_container} already exists but is not owned by this project"
  fi
done

bind_address="${LLM_STUDIO_BIND_ADDRESS:-$(env_value LLM_STUDIO_BIND_ADDRESS 127.0.0.1)}"
port="${LLM_STUDIO_PORT:-$(env_value LLM_STUDIO_PORT 18080)}"
data_dir="${LLM_STUDIO_DATA_DIR:-$(env_value LLM_STUDIO_DATA_DIR /opt/data/llm-studio)}"
traefik_mode="${LLM_STUDIO_TRAEFIK_MODE:-$(env_value LLM_STUDIO_TRAEFIK_MODE local)}"
observability_enabled="${LLM_STUDIO_OBSERVABILITY_ENABLED:-$(env_value LLM_STUDIO_OBSERVABILITY_ENABLED false)}"
observability_bind="${LLM_STUDIO_OBSERVABILITY_BIND_ADDRESS:-$(env_value LLM_STUDIO_OBSERVABILITY_BIND_ADDRESS 127.0.0.1)}"
observability_port="${LLM_STUDIO_OBSERVABILITY_PORT:-$(env_value LLM_STUDIO_OBSERVABILITY_PORT 15080)}"
observability_retention="${LLM_STUDIO_OBSERVABILITY_RETENTION_DAYS:-$(env_value LLM_STUDIO_OBSERVABILITY_RETENTION_DAYS 30)}"

[[ "${traefik_mode}" == local || "${traefik_mode}" == internet ]] \
  || die 'LLM_STUDIO_TRAEFIK_MODE must be local or internet'
[[ "${observability_enabled}" == true || "${observability_enabled}" == false ]] \
  || die 'LLM_STUDIO_OBSERVABILITY_ENABLED must be true or false'
if [[ "${observability_enabled}" == true ]]; then
  assert_safe_bind_address "${observability_bind}"
  [[ "${observability_port}" =~ ^[0-9]+$ ]] && (( observability_port >= 1024 && observability_port <= 65535 )) \
    || die 'LLM_STUDIO_OBSERVABILITY_PORT must be an integer from 1024 through 65535'
  [[ "${observability_retention}" =~ ^[0-9]+$ ]] && (( observability_retention >= 3 && observability_retention <= 3650 )) \
    || die 'LLM_STUDIO_OBSERVABILITY_RETENTION_DAYS must be from 3 through 3650'
  if ss -H -ltn | awk -v wanted_port="${observability_port}" '$4 ~ (":" wanted_port "$") { found = 1 } END { exit(found ? 0 : 1) }'; then
    docker ps --format '{{.Names}}' | grep -qx llm-studio-openobserve \
      || die "observability TCP port ${observability_port} is already in use"
  fi
fi
if [[ "${traefik_mode}" == local ]]; then
  assert_safe_bind_address "${bind_address}"
  [[ "${port}" =~ ^[0-9]+$ ]] && (( port >= 1024 && port <= 65535 )) \
    || die 'LLM_STUDIO_PORT must be an integer from 1024 through 65535'
  if [[ "${bind_address}" != 127.0.0.1 ]]; then
    ip addr show | grep -Fq "${bind_address}" \
      || die "Private bind address ${bind_address} is not assigned to this host"
  fi
else
  public_domain="${LLM_STUDIO_PUBLIC_DOMAIN:-$(env_value LLM_STUDIO_PUBLIC_DOMAIN '')}"
  acme_email="${LLM_STUDIO_ACME_EMAIL:-$(env_value LLM_STUDIO_ACME_EMAIL '')}"
  internet_bind="${LLM_STUDIO_INTERNET_BIND_ADDRESS:-$(env_value LLM_STUDIO_INTERNET_BIND_ADDRESS 0.0.0.0)}"
  [[ "${public_domain}" =~ ^[A-Za-z0-9.-]+$ && "${public_domain}" == *.* && "${public_domain}" != *..* ]] \
    || die 'internet mode requires a valid DNS hostname in LLM_STUDIO_PUBLIC_DOMAIN'
  [[ "${acme_email}" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] \
    || die 'internet mode requires a valid LLM_STUDIO_ACME_EMAIL'
  [[ "${internet_bind}" == 0.0.0.0 ]] \
    || die 'internet mode currently requires LLM_STUDIO_INTERNET_BIND_ADDRESS=0.0.0.0'
fi

if [[ "${traefik_mode}" == local ]]; then
  if ss -H -ltn | awk -v wanted_port="${port}" '$4 ~ (":" wanted_port "$") { found = 1 } END { exit(found ? 0 : 1) }'; then
    docker ps --format '{{.Names}}' | grep -qx llm-studio-traefik-local \
      || die "TCP port ${port} is already in use"
  fi
else
  for public_port in 80 443; do
    if ss -H -ltn | awk -v wanted_port="${public_port}" '$4 ~ (":" wanted_port "$") { found = 1 } END { exit(found ? 0 : 1) }'; then
      docker ps --format '{{.Names}}' | grep -qx llm-studio-traefik-internet \
        || die "public TCP port ${public_port} is already in use; refusing to conflict with Hermes or another stack"
    fi
  done
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
for directory in models datasets training checkpoints rag vectorstore documents api logs notebooks scripts configs experiments backups openobserve otel; do
  install -d -m 0750 -- "${data_dir}/${directory}"
done
install -d -m 0700 -- "${data_dir}/traefik"
if [[ ! -e "${data_dir}/traefik/acme.json" ]]; then
  install -m 0600 /dev/null "${data_dir}/traefik/acme.json"
fi
if [[ "${traefik_mode}" == internet ]]; then
  sed "s/__LLM_STUDIO_DOMAIN__/${public_domain}/g" \
    "${PROJECT_ROOT}/configs/traefik/dynamic/llm-studio.internet.yml.template" \
    >"${data_dir}/configs/traefik-internet.yml"
  chmod 0644 "${data_dir}/configs/traefik-internet.yml"
fi

api_key="${LLM_STUDIO_API_KEY:-$(env_value LLM_STUDIO_API_KEY '')}"
if [[ -z "${api_key}" || "${api_key}" == replace-with-* ]]; then
  api_key="$(openssl rand -hex 32)"
fi
(( ${#api_key} >= 32 )) || die 'LLM_STUDIO_API_KEY must contain at least 32 characters'
[[ "${api_key}" =~ ^[A-Za-z0-9._-]+$ ]] \
  || die 'LLM_STUDIO_API_KEY may contain only letters, numbers, dot, underscore, and hyphen'

openobserve_email="${LLM_STUDIO_OPENOBSERVE_EMAIL:-$(env_value LLM_STUDIO_OPENOBSERVE_EMAIL admin@llm-studio.local)}"
openobserve_password="${LLM_STUDIO_OPENOBSERVE_PASSWORD:-$(env_value LLM_STUDIO_OPENOBSERVE_PASSWORD '')}"
if [[ -z "${openobserve_password}" || "${openobserve_password}" == replace-with-* ]]; then
  openobserve_password="Oo1!$(openssl rand -hex 24)"
fi
openobserve_auth="$(python3 - "${openobserve_email}" "${openobserve_password}" <<'PY'
import base64
import sys
print(base64.b64encode(f"{sys.argv[1]}:{sys.argv[2]}".encode()).decode())
PY
)"

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
  printf 'LLM_STUDIO_TRAEFIK_MODE=%s\n' "${traefik_mode}"
  printf 'LLM_STUDIO_INTERNET_BIND_ADDRESS=%s\n' "$(env_value LLM_STUDIO_INTERNET_BIND_ADDRESS 0.0.0.0)"
  printf 'LLM_STUDIO_PUBLIC_DOMAIN=%s\n' "${public_domain:-$(env_value LLM_STUDIO_PUBLIC_DOMAIN llm.example.com)}"
  printf 'LLM_STUDIO_ACME_EMAIL=%s\n' "${acme_email:-$(env_value LLM_STUDIO_ACME_EMAIL admin@example.com)}"
  printf 'LLM_STUDIO_HTTP_PORT=80\n'
  printf 'LLM_STUDIO_HTTPS_PORT=443\n'
  printf 'LLM_STUDIO_ACME_CA_SERVER=%s\n' "$(env_value LLM_STUDIO_ACME_CA_SERVER https://acme-v02.api.letsencrypt.org/directory)"
  printf 'LLM_STUDIO_DATA_DIR=%s\n' "${data_dir}"
  printf 'LLM_STUDIO_API_KEY=%s\n' "${api_key}"
  printf 'LLM_STUDIO_APP_UID=%s\n' "${app_uid}"
  printf 'LLM_STUDIO_APP_GID=%s\n' "${app_gid}"
  printf 'MODEL_ID=%s\n' "$(env_value MODEL_ID Qwen/Qwen3.5-0.8B)"
  printf 'MODEL_BACKEND=%s\n' "$(env_value MODEL_BACKEND multimodal)"
  printf 'MODEL_DTYPE=%s\n' "$(env_value MODEL_DTYPE auto)"
  printf 'MODEL_REVISION=%s\n' "$(env_value MODEL_REVISION main)"
  printf 'MODEL_ALLOWED_MODELS=%s\n' "$(env_value MODEL_ALLOWED_MODELS Qwen/Qwen3.5-0.8B,Qwen/Qwen3.5-2B)"
  printf 'MODEL_PRELOAD_MODELS=%s\n' "$(env_value MODEL_PRELOAD_MODELS qwen35-0.8b,qwen35-2b)"
  printf 'MODEL_IDLE_UNLOAD_SECONDS=%s\n' "$(env_value MODEL_IDLE_UNLOAD_SECONDS 3600)"
  printf 'MODEL_GGUF_CONTEXT_TOKENS=%s\n' "$(env_value MODEL_GGUF_CONTEXT_TOKENS 32768)"
  printf 'MODEL_KV_CACHE_BYTES=%s\n' "$(env_value MODEL_KV_CACHE_BYTES 2147483648)"
  printf 'MODEL_CONTEXT_TOKENS=%s\n' "$(env_value MODEL_CONTEXT_TOKENS 262144)"
  printf 'MODEL_MAX_INPUT_TOKENS=%s\n' "$(env_value MODEL_MAX_INPUT_TOKENS 262144)"
  printf 'MODEL_MAX_NEW_TOKENS=%s\n' "$(env_value MODEL_MAX_NEW_TOKENS 2048)"
  printf 'MODEL_MIN_NEW_TOKENS=%s\n' "$(env_value MODEL_MIN_NEW_TOKENS 16)"
  printf 'MODEL_LOAD_ON_START=%s\n' "$(env_value MODEL_LOAD_ON_START false)"
  printf 'LLM_STUDIO_CPU_THREADS=%s\n' "$(env_value LLM_STUDIO_CPU_THREADS 3)"
  printf 'LLM_STUDIO_REQUEST_TIMEOUT_SECONDS=%s\n' "$(env_value LLM_STUDIO_REQUEST_TIMEOUT_SECONDS 900)"
  printf 'LLM_STUDIO_MAX_CONCURRENT_REQUESTS=%s\n' "$(env_value LLM_STUDIO_MAX_CONCURRENT_REQUESTS 1)"
  printf 'LLM_STUDIO_QUEUE_TIMEOUT_SECONDS=%s\n' "$(env_value LLM_STUDIO_QUEUE_TIMEOUT_SECONDS 900)"
  printf 'LLM_STUDIO_REQUEST_TRACE_LOGGING=%s\n' "$(env_value LLM_STUDIO_REQUEST_TRACE_LOGGING true)"
  printf 'LLM_STUDIO_REQUEST_TRACE_MAX_CONTENT_CHARS=%s\n' "$(env_value LLM_STUDIO_REQUEST_TRACE_MAX_CONTENT_CHARS 32768)"
  printf 'LLM_STUDIO_OBSERVABILITY_ENABLED=%s\n' "${observability_enabled}"
  printf 'LLM_STUDIO_OBSERVABILITY_BIND_ADDRESS=%s\n' "${observability_bind}"
  printf 'LLM_STUDIO_OBSERVABILITY_PORT=%s\n' "${observability_port}"
  printf 'LLM_STUDIO_OBSERVABILITY_RETENTION_DAYS=%s\n' "${observability_retention}"
  printf 'LLM_STUDIO_OPENOBSERVE_EMAIL=%s\n' "${openobserve_email}"
  printf 'LLM_STUDIO_OPENOBSERVE_PASSWORD=%s\n' "${openobserve_password}"
  printf 'LLM_STUDIO_OPENOBSERVE_AUTH=%s\n' "${openobserve_auth}"
  printf 'LLM_STUDIO_OPENOBSERVE_IMAGE=%s\n' "$(env_value LLM_STUDIO_OPENOBSERVE_IMAGE public.ecr.aws/zinclabs/openobserve:v1.0.3)"
  printf 'LLM_STUDIO_OTEL_COLLECTOR_IMAGE=%s\n' "$(env_value LLM_STUDIO_OTEL_COLLECTOR_IMAGE otel/opentelemetry-collector-contrib:0.153.0)"
} >"${env_tmp}"
chmod 0600 "${env_tmp}"
mv -f -- "${env_tmp}" "${ENV_FILE}"
if [[ "$(id -u)" == 0 && -n "${SUDO_UID:-}" ]]; then
  chown "${SUDO_UID}:${SUDO_GID}" -- "${ENV_FILE}"
fi
trap - EXIT

log 'Phase 4/6: validating the Docker Compose configuration'
# These files contain routing and collector configuration only (no secrets).
# A caller's restrictive umask or archive extraction can otherwise leave them
# unreadable to the non-root processes used by the proxy and collector images.
chmod 0755 \
  "${PROJECT_ROOT}/configs" \
  "${PROJECT_ROOT}/configs/traefik" \
  "${PROJECT_ROOT}/configs/traefik/dynamic"
chmod 0644 \
  "${PROJECT_ROOT}/configs/otel-collector.yml" \
  "${PROJECT_ROOT}/configs/traefik/traefik.yml" \
  "${PROJECT_ROOT}/configs/traefik/traefik.internet.yml" \
  "${PROJECT_ROOT}/configs/traefik/dynamic/llm-studio.yml" \
  "${PROJECT_ROOT}/configs/traefik/dynamic/llm-studio.internet.yml.template"
compose config --quiet

if [[ "${LLM_STUDIO_SETUP_NO_START:-false}" == true ]]; then
  log 'LLM_STUDIO_SETUP_NO_START=true: validation complete; images and services were not started.'
  exit 0
fi

log 'Phase 5/6: building and starting only the llm-studio project'
compose build
if [[ "${traefik_mode}" == local ]]; then
  docker compose --project-name "${COMPOSE_PROJECT}" --env-file "${ENV_FILE}" --file "${COMPOSE_FILE}" --profile internet rm --stop --force traefik-internet >/dev/null 2>&1 || true
else
  docker compose --project-name "${COMPOSE_PROJECT}" --env-file "${ENV_FILE}" --file "${COMPOSE_FILE}" --profile local rm --stop --force traefik-local >/dev/null 2>&1 || true
fi
IFS=',' read -r -a preload_models <<<"$(env_value MODEL_PRELOAD_MODELS qwen35-0.8b,qwen35-2b)"
if (( ${#preload_models[@]} > 0 )); then
  "${SCRIPT_DIR}/models.py" install "${preload_models[@]}"
fi
compose up --detach

log 'Phase 6/6: waiting for health and running an authenticated smoke test'
service_url="$(base_url)"
deadline=$((SECONDS + 240))
until curl --silent --show-error --fail --max-time 5 "${service_url}/health" >/dev/null; do
  if (( SECONDS >= deadline )); then
    compose ps >&2 || true
    compose logs --tail 80 api >&2 || true
    die 'API health check did not pass within 240 seconds'
  fi
  sleep 2
done

"${SCRIPT_DIR}/smoke_test.sh"

log 'Setup complete.'
printf 'Mode: %s\n' "${traefik_mode}"
printf 'Base URL: %s/v1\n' "${service_url}"
printf 'API key: stored in %s (mode 0600; value not printed)\n' "${ENV_FILE}"
printf 'Model: %s (downloaded lazily on the first chat request)\n' "$(env_value MODEL_ID Qwen/Qwen3.5-0.8B)"
printf 'Environment report: %s\n' "${PROJECT_ROOT}/docs/environment.md"
if [[ "${observability_enabled}" == true ]]; then
  printf 'Observability UI: http://%s:%s (credentials are stored only in %s)\n' \
    "${observability_bind}" "${observability_port}" "${ENV_FILE}"
fi
