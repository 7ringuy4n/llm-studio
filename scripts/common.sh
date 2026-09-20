#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly COMPOSE_FILE="${PROJECT_ROOT}/compose.yaml"
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

compose() {
  docker compose \
    --project-name "${COMPOSE_PROJECT}" \
    --env-file "${ENV_FILE}" \
    --file "${COMPOSE_FILE}" \
    "$@"
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
