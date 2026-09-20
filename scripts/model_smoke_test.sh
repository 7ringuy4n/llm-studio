#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
assert_env_file
require_command curl

bind_address="$(env_value LLM_STUDIO_BIND_ADDRESS 127.0.0.1)"
port="$(env_value LLM_STUDIO_PORT 18080)"
api_key="$(env_value LLM_STUDIO_API_KEY '')"
model_id="$(env_value MODEL_ID Qwen/Qwen3-0.6B)"

response_file="$(mktemp)"
trap 'rm -f -- "${response_file}"' EXIT

curl --silent --show-error --fail-with-body --max-time 600 \
  --header "Authorization: Bearer ${api_key}" \
  --header 'Content-Type: application/json' \
  --data "{\"model\":\"${model_id}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly: ready\"}],\"max_tokens\":8,\"temperature\":0}" \
  "http://${bind_address}:${port}/v1/chat/completions" >"${response_file}"

python3 - "${response_file}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
content = payload["choices"][0]["message"]["content"]
if not isinstance(content, str) or not content.strip():
    raise SystemExit("Model returned an empty completion")
print("Model generation smoke test passed.")
PY

