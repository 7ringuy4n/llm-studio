#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
assert_env_file
require_command openssl

new_key="$(openssl rand -hex 32)"
env_tmp="$(mktemp "${PROJECT_ROOT}/.env.tmp.XXXXXX")"
trap 'rm -f -- "${env_tmp}"' EXIT

awk -F= -v new_key="${new_key}" '
  BEGIN { replaced = 0 }
  $1 == "LLM_STUDIO_API_KEY" { print "LLM_STUDIO_API_KEY=" new_key; replaced = 1; next }
  { print }
  END { if (!replaced) print "LLM_STUDIO_API_KEY=" new_key }
' "${ENV_FILE}" >"${env_tmp}"
chmod 0600 "${env_tmp}"
mv -f -- "${env_tmp}" "${ENV_FILE}"
trap - EXIT

compose up --detach --force-recreate api
log "API key rotated. Update clients from ${ENV_FILE}; the key value was not printed."

