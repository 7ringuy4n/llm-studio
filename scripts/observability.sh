#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/common.sh"
assert_env_file

action="${1:-}"
case "${action}" in
  enable)
    python3 - "${ENV_FILE}" <<'PY'
import base64
from pathlib import Path
import secrets
import sys
path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
values = {}
for line in lines:
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        values[key] = value
email = values.get("LLM_STUDIO_OPENOBSERVE_EMAIL") or "admin@llm-studio.local"
password = values.get("LLM_STUDIO_OPENOBSERVE_PASSWORD", "")
if not password or password.startswith("replace-with-"):
    password = "Oo1!" + secrets.token_hex(24)
updates = {
    "LLM_STUDIO_OBSERVABILITY_ENABLED": "true",
    "LLM_STUDIO_OBSERVABILITY_BIND_ADDRESS": values.get("LLM_STUDIO_OBSERVABILITY_BIND_ADDRESS", "127.0.0.1"),
    "LLM_STUDIO_OBSERVABILITY_PORT": values.get("LLM_STUDIO_OBSERVABILITY_PORT", "15080"),
    "LLM_STUDIO_OBSERVABILITY_RETENTION_DAYS": values.get("LLM_STUDIO_OBSERVABILITY_RETENTION_DAYS", "30"),
    "LLM_STUDIO_OPENOBSERVE_EMAIL": email,
    "LLM_STUDIO_OPENOBSERVE_PASSWORD": password,
    "LLM_STUDIO_OPENOBSERVE_AUTH": base64.b64encode(f"{email}:{password}".encode()).decode(),
    "LLM_STUDIO_OPENOBSERVE_IMAGE": values.get("LLM_STUDIO_OPENOBSERVE_IMAGE", "public.ecr.aws/zinclabs/openobserve:v1.0.3"),
    "LLM_STUDIO_OTEL_COLLECTOR_IMAGE": values.get("LLM_STUDIO_OTEL_COLLECTOR_IMAGE", "otel/opentelemetry-collector-contrib:0.153.0"),
}
seen = set()
for index, line in enumerate(lines):
    key = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else None
    if key in updates:
        lines[index] = f"{key}={updates[key]}"
        seen.add(key)
lines.extend(f"{key}={value}" for key, value in updates.items() if key not in seen)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
    chmod 0600 "${ENV_FILE}"
    compose up --detach openobserve otel-collector
    printf 'OpenObserve: http://%s:%s\n' \
      "$(env_value LLM_STUDIO_OBSERVABILITY_BIND_ADDRESS 127.0.0.1)" \
      "$(env_value LLM_STUDIO_OBSERVABILITY_PORT 15080)"
    ;;
  disable)
    docker compose --project-name "${COMPOSE_PROJECT}" --env-file "${ENV_FILE}" \
      --file "${COMPOSE_FILE}" --profile observability stop openobserve otel-collector
    python3 - "${ENV_FILE}" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
lines = [
    "LLM_STUDIO_OBSERVABILITY_ENABLED=false" if line.startswith("LLM_STUDIO_OBSERVABILITY_ENABLED=") else line
    for line in path.read_text(encoding="utf-8").splitlines()
]
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
    chmod 0600 "${ENV_FILE}"
    ;;
  *)
    die 'usage: scripts/observability.sh enable|disable'
    ;;
esac
