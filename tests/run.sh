#!/usr/bin/env bash

set -Eeuo pipefail

readonly TEST_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PROJECT_ROOT="$(cd -- "${TEST_DIR}/.." && pwd -P)"

cd "${PROJECT_ROOT}"

for script in scripts/*.sh tests/*.sh; do
  bash -n "${script}"
done

python3 -m compileall -q api
python3 -m py_compile tests/web_search_contract.py
python3 tests/dsh_config_unit.py

grep -Fq 'Qwen/Qwen3.5-0.8B' compose.yaml
grep -Fq 'AutoModelForMultimodalLM' api/model_runtime.py
grep -Fq 'AutoModelForCausalLM' api/model_runtime.py
grep -Fq 'MODEL_BACKEND=multimodal' .env.example
grep -Fq 'MODEL_CONTEXT_TOKENS=262144' .env.example
grep -Fq 'MODEL_IDLE_UNLOAD_SECONDS=3600' .env.example
grep -Fq 'llama-cpp-python==0.3.35' requirements.txt
grep -Fq 'MODEL_KV_CACHE_BYTES=2147483648' .env.example
grep -Fq 'LLM_STUDIO_QUEUE_TIMEOUT_SECONDS=900' .env.example
grep -Fq 'Qwen/Qwen3-8B' configs/models.json
grep -Fq 'DeepSeek-R1-Distill-Qwen-7B' configs/models.json
grep -Fq 'Llama-3.1-8B-Instruct' configs/models.json
grep -Fq 'Qwen/Qwen3.5-2B' configs/models.json
grep -Fq 'self._unload_if_idle' api/model_runtime.py
grep -Fq 'image_url.url must be an embedded PNG, JPEG, or WebP data URL' api/schemas.py
grep -Fq 'transformers==5.17.0' requirements.txt
grep -Fq '/v1/chat/completions' api/app.py
grep -Fq 'chat_template_kwargs: ChatTemplateKwargs | None = None' api/schemas.py
grep -Fq '"enable_thinking": request.thinking_enabled and spec.reasoning' api/model_runtime.py
grep -Fq 'Authorization: Bearer' scripts/smoke_test.sh
grep -Fq 'cap_drop:' compose.yaml
grep -Fq 'no-new-privileges:true' compose.yaml
grep -Fq 'container_name: llm-studio-traefik-local' compose.yaml
grep -Fq 'container_name: llm-studio-traefik-internet' compose.yaml
grep -Fq 'profiles: ["local"]' compose.yaml
grep -Fq 'profiles: ["internet"]' compose.yaml
grep -Fq 'certResolver: letsencrypt' configs/traefik/dynamic/llm-studio.internet.yml.template
grep -Fq 'LLM_STUDIO_TRAEFIK_MODE=local' .env.example
grep -Fq './configs/traefik/traefik.yml:/etc/traefik/traefik.yml:ro' compose.yaml
grep -Fq 'url: "http://api:8000"' configs/traefik/dynamic/llm-studio.yml
grep -Fq 'Docker is not installed; run sudo ./scripts/install_docker.sh' scripts/setup.sh
grep -Fq 'download.docker.com/linux/' scripts/install_docker.sh
grep -Fq 'BACKUP_COMPLETE' scripts/backup_data.sh scripts/restore_data.sh
grep -Fq 'sha256sum --check SHA256SUMS' scripts/restore_data.sh
grep -Fq 'first_token_latency_ms' api/model_runtime.py api/app.py
grep -Fq 'cache_hit_percent' api/app.py
grep -Fq 'source_ip' api/tracing.py
grep -Fq 'profiles: ["observability"]' compose.yaml
grep -Fq 'public.ecr.aws/zinclabs/openobserve:v1.0.3' compose.yaml .env.example
grep -Fq 'otel/opentelemetry-collector-contrib:0.153.0' compose.yaml .env.example
grep -Fq 'llm_studio_requests' configs/otel-collector.yml
grep -Fq 'tool_choice": "required"' tests/web_search_contract.py

if rg -n 'SlidingWindowRateLimiter|rate_limiter|RATE_LIMIT_PER_MINUTE' api scripts .env.example compose.yaml; then
  printf 'Rate-limit removal check failed: application limiter references remain.\n' >&2
  exit 1
fi

if grep -Eq '/var/run/docker.sock|hermes.*(volume|network)' compose.yaml configs/traefik/traefik.yml configs/traefik/dynamic/llm-studio.yml; then
  printf 'Isolation check failed: prohibited Docker socket or Hermes attachment found.\n' >&2
  exit 1
fi

if rg -i --no-ignore 'AI_LAB|ai-lab|ai_lab|ai\.lab|AI[ -]lab' \
  --glob '!.git/**' --glob '!.agents/**' --glob '!.codex/**' \
  --glob '!tests/run.sh' .; then
  printf 'Naming check failed: legacy project identifiers remain.\n' >&2
  exit 1
fi

test_env="$(mktemp)"
trap 'rm -f -- "${test_env}"; find api -type d -name __pycache__ -prune -exec rm -rf {} +' EXIT
sed \
  -e 's|LLM_STUDIO_DATA_DIR=/opt/data/llm-studio|LLM_STUDIO_DATA_DIR=/tmp/llm-studio-test|' \
  -e 's|replace-with-at-least-32-random-characters|0123456789abcdef0123456789abcdef|' \
  .env.example >"${test_env}"

docker compose --project-name llm-studio-test --env-file "${test_env}" --file compose.yaml config --quiet

printf 'Static tests passed. No container was started and no model was downloaded.\n'
