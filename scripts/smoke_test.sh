#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
assert_env_file
require_command curl

api_base_url="$(base_url)"
api_key="$(env_value LLM_STUDIO_API_KEY '')"
[[ -n "${api_key}" ]] || die 'LLM_STUDIO_API_KEY is missing'

curl --silent --show-error --fail --max-time 10 \
  --header "Authorization: Bearer ${api_key}" \
  "${api_base_url}/v1/models" >/dev/null

if curl --silent --output /dev/null --write-out '%{http_code}' --max-time 10 \
  "${api_base_url}/v1/models" | grep -qv '^401$'; then
  die 'Unauthenticated request was not rejected with HTTP 401'
fi

log 'Smoke test passed: authenticated model listing works and missing credentials are rejected.'
