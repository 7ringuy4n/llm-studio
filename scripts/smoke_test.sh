#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
assert_env_file
require_command curl

bind_address="$(env_value LLM_STUDIO_BIND_ADDRESS 127.0.0.1)"
port="$(env_value LLM_STUDIO_PORT 18080)"
api_key="$(env_value LLM_STUDIO_API_KEY '')"
[[ -n "${api_key}" ]] || die 'LLM_STUDIO_API_KEY is missing'

curl --silent --show-error --fail --max-time 10 \
  --header "Authorization: Bearer ${api_key}" \
  "http://${bind_address}:${port}/v1/models" >/dev/null

if curl --silent --output /dev/null --write-out '%{http_code}' --max-time 10 \
  "http://${bind_address}:${port}/v1/models" | grep -qv '^401$'; then
  die 'Unauthenticated request was not rejected with HTTP 401'
fi

log 'Smoke test passed: authenticated model listing works and missing credentials are rejected.'

