#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly COMPOSE_FILE="${PROJECT_ROOT}/compose.yaml"
readonly COMPOSE_GPU_FILE="${PROJECT_ROOT}/compose.gpu.yaml"
readonly ENV_FILE="${PROJECT_ROOT}/.env"
readonly COMPOSE_PROJECT="llm-studio"

log() {
  printf '[llm-studio] %s\n' "$*"
}

die() {
  printf '[llm-studio] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

env_value() {
  local key="$1"
  local fallback="${2:-}"
  local value
  if [[ -f "${ENV_FILE}" ]]; then
    value="$(awk -F= -v wanted="${key}" '$1 == wanted {sub(/^[^=]*=/, ""); print; exit}' "${ENV_FILE}")"
  fi
  printf '%s' "${value:-${fallback}}"
}

host_has_nvidia_gpu() {
  command -v nvidia-smi >/dev/null 2>&1 || return 1
  nvidia-smi >/dev/null 2>&1
}

docker_nvidia_runtime_ready() {
  docker info 2>/dev/null | grep -Eqi 'Runtimes:.*nvidia|nvidia\.com/gpu' \
    || docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -qi nvidia
}

# Resolve auto|cpu|cuda → cpu|cuda for .env / Compose. Prints the resolved value.
resolve_accelerator() {
  local requested="${1:-auto}"
  case "${requested}" in
    cpu)
      printf 'cpu'
      return 0
      ;;
    cuda)
      host_has_nvidia_gpu || die 'LLM_STUDIO_ACCELERATOR=cuda but nvidia-smi failed'
      docker_nvidia_runtime_ready \
        || die 'LLM_STUDIO_ACCELERATOR=cuda but Docker NVIDIA runtime is missing (install nvidia-container-toolkit)'
      printf 'cuda'
      return 0
      ;;
    auto)
      if host_has_nvidia_gpu && docker_nvidia_runtime_ready; then
        printf 'cuda'
      else
        if host_has_nvidia_gpu; then
          log 'WARNING: NVIDIA GPU detected but Docker cannot use it; falling back to cpu (install nvidia-container-toolkit)'
        fi
        printf 'cpu'
      fi
      return 0
      ;;
    *)
      die 'LLM_STUDIO_ACCELERATOR must be auto, cpu, or cuda'
      ;;
  esac
}

compose() {
  local traefik_mode observability_enabled accelerator
  traefik_mode="$(env_value LLM_STUDIO_TRAEFIK_MODE local)"
  observability_enabled="$(env_value LLM_STUDIO_OBSERVABILITY_ENABLED false)"
  accelerator="$(env_value LLM_STUDIO_ACCELERATOR cpu)"
  local -a command=(docker compose --project-name "${COMPOSE_PROJECT}" --env-file "${ENV_FILE}" --file "${COMPOSE_FILE}")
  if [[ "${accelerator}" == cuda ]]; then
    command+=(--file "${COMPOSE_GPU_FILE}")
  fi
  command+=(--profile "${traefik_mode}")
  if [[ "${observability_enabled}" == true ]]; then
    command+=(--profile observability)
  fi
  "${command[@]}" "$@"
}

base_url() {
  local traefik_mode
  traefik_mode="$(env_value LLM_STUDIO_TRAEFIK_MODE local)"
  if [[ "${traefik_mode}" == internet ]]; then
    printf 'https://%s' "$(env_value LLM_STUDIO_PUBLIC_DOMAIN '')"
  else
    printf 'http://%s:%s' \
      "$(env_value LLM_STUDIO_BIND_ADDRESS 127.0.0.1)" \
      "$(env_value LLM_STUDIO_PORT 18080)"
  fi
}

assert_safe_bind_address() {
  local bind_address="$1"
  python3 - "${bind_address}" <<'PY'
import ipaddress
import sys

try:
    address = ipaddress.ip_address(sys.argv[1])
except ValueError:
    raise SystemExit("LLM_STUDIO_BIND_ADDRESS must be a literal IPv4 address")

if not isinstance(address, ipaddress.IPv4Address):
    raise SystemExit("LLM_STUDIO_BIND_ADDRESS currently supports IPv4 only")

if address.is_unspecified or address.is_multicast or address.is_global:
    raise SystemExit(
        "Refusing a wildcard, multicast, or public LLM_STUDIO_BIND_ADDRESS; "
        "use loopback or the explicit OpenVPN/private IP"
    )

if not (address.is_loopback or address.is_private):
    raise SystemExit("LLM_STUDIO_BIND_ADDRESS must be loopback or private")
PY
}

assert_env_file() {
  [[ -f "${ENV_FILE}" ]] || die "${ENV_FILE} does not exist; run scripts/setup.sh first"
}
