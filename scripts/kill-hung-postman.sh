#!/usr/bin/env bash

set -Eeuo pipefail

readonly POSTMAN_APP_ID="com.getpostman.Postman"
readonly WAIT_SECONDS="${POSTMAN_KILL_TIMEOUT_SECONDS:-5}"

log() {
  printf '[postman-cleanup] %s\n' "$*"
}

if [[ ! "${WAIT_SECONDS}" =~ ^[1-9][0-9]*$ ]] || (( WAIT_SECONDS > 30 )); then
  printf '[postman-cleanup] ERROR: POSTMAN_KILL_TIMEOUT_SECONDS must be an integer from 1 to 30.\n' >&2
  exit 2
fi

postman_pids() {
  local proc pid owner
  for proc in /proc/[0-9]*; do
    pid="${proc##*/}"
    [[ "${pid}" != "$$" && -r "${proc}/environ" ]] || continue
    owner="$(stat -c '%u' "${proc}" 2>/dev/null || true)"
    [[ "${owner}" == "${EUID}" ]] || continue
    if tr '\0' '\n' 2>/dev/null <"${proc}/environ" | grep -Fqx "FLATPAK_ID=${POSTMAN_APP_ID}"; then
      printf '%s\n' "${pid}"
    fi
  done
}

if command -v flatpak >/dev/null 2>&1; then
  if flatpak ps --columns=application 2>/dev/null | grep -Fqx "${POSTMAN_APP_ID}"; then
    log "Asking Flatpak to stop every Postman instance."
    flatpak kill "${POSTMAN_APP_ID}" 2>/dev/null || true
  fi
fi

mapfile -t pids < <(postman_pids)
if (( ${#pids[@]} == 0 )); then
  log "No Postman processes remain."
  exit 0
fi

log "Sending TERM to ${#pids[@]} remaining Postman process(es): ${pids[*]}"
kill -TERM -- "${pids[@]}" 2>/dev/null || true

deadline=$((SECONDS + WAIT_SECONDS))
while (( SECONDS < deadline )); do
  mapfile -t pids < <(postman_pids)
  (( ${#pids[@]} == 0 )) && break
  sleep 0.2
done

mapfile -t pids < <(postman_pids)
if (( ${#pids[@]} > 0 )); then
  log "Force-killing ${#pids[@]} unresponsive Postman process(es): ${pids[*]}"
  kill -KILL -- "${pids[@]}" 2>/dev/null || true
fi

mapfile -t pids < <(postman_pids)
if (( ${#pids[@]} > 0 )); then
  printf '[postman-cleanup] ERROR: Postman processes still remain: %s\n' "${pids[*]}" >&2
  exit 1
fi

log "All Postman processes stopped."
