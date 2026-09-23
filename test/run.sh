#!/usr/bin/env bash
# Offline static gate for llm-studio. Prints running test case N/M.

set -Eeuo pipefail

readonly TEST_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PROJECT_ROOT="$(cd -- "${TEST_DIR}/.." && pwd -P)"
readonly CASE_TOTAL=56

cd "${PROJECT_ROOT}"

case_n=0
_progress() {
  case_n=$((case_n + 1))
  printf 'running test case %s/%s: %s\n' "${case_n}" "${CASE_TOTAL}" "$*"
}

_progress "bash -n scripts/*.sh"
for script in scripts/*.sh; do
  bash -n "${script}"
done

_progress "python3 -m compileall -q api"
python3 -m compileall -q api

_progress "py_compile test/scripts/web_search_contract.py"
python3 -m py_compile test/scripts/web_search_contract.py

_progress "python3 test/scripts/dsh_config_unit.py"
python3 test/scripts/dsh_config_unit.py

_progress "grep Qwen/Qwen3.5-0.8B compose.yaml"
grep -Fq 'Qwen/Qwen3.5-0.8B' compose.yaml
_progress "grep AutoModelForMultimodalLM"
grep -Fq 'AutoModelForMultimodalLM' api/model_runtime.py
_progress "grep AutoModelForCausalLM"
grep -Fq 'AutoModelForCausalLM' api/model_runtime.py
_progress "grep MODEL_BACKEND=multimodal"
grep -Fq 'MODEL_BACKEND=multimodal' .env.example
_progress "grep MODEL_CONTEXT_TOKENS=262144"
grep -Fq 'MODEL_CONTEXT_TOKENS=262144' .env.example
_progress "grep MODEL_IDLE_UNLOAD_SECONDS=3600"
grep -Fq 'MODEL_IDLE_UNLOAD_SECONDS=3600' .env.example
_progress "grep llama-cpp-python==0.3.35"
grep -Fq 'llama-cpp-python==0.3.35' requirements.txt
_progress "grep MODEL_KV_CACHE_BYTES"
grep -Fq 'MODEL_KV_CACHE_BYTES=2147483648' .env.example
_progress "grep LLM_STUDIO_QUEUE_TIMEOUT_SECONDS"
grep -Fq 'LLM_STUDIO_QUEUE_TIMEOUT_SECONDS=900' .env.example
_progress "grep Qwen/Qwen3-8B catalog"
grep -Fq 'Qwen/Qwen3-8B' configs/models.json
_progress "grep DeepSeek-R1 catalog"
grep -Fq 'DeepSeek-R1-Distill-Qwen-7B' configs/models.json
_progress "grep Llama-3.1-8B catalog"
grep -Fq 'Llama-3.1-8B-Instruct' configs/models.json
_progress "grep Qwen/Qwen3.5-2B catalog"
grep -Fq 'Qwen/Qwen3.5-2B' configs/models.json
_progress "grep idle unload"
grep -Fq 'self._unload_if_idle' api/model_runtime.py
_progress "grep image data-URL validation"
grep -Fq 'image_url.url must be an embedded PNG, JPEG, or WebP data URL' api/schemas.py
_progress "grep transformers==5.17.0"
grep -Fq 'transformers==5.17.0' requirements.txt
_progress "grep /v1/chat/completions"
grep -Fq '/v1/chat/completions' api/app.py
_progress "grep chat_template_kwargs schema"
grep -Fq 'chat_template_kwargs: ChatTemplateKwargs | None = None' api/schemas.py
_progress "grep enable_thinking wiring"
grep -Fq '"enable_thinking": request.thinking_enabled and spec.reasoning' api/model_runtime.py
_progress "grep Authorization Bearer smoke"
grep -Fq 'Authorization: Bearer' scripts/smoke_test.sh
_progress "grep cap_drop"
grep -Fq 'cap_drop:' compose.yaml
_progress "grep no-new-privileges"
grep -Fq 'no-new-privileges:true' compose.yaml
_progress "grep traefik-local container"
grep -Fq 'container_name: llm-studio-traefik-local' compose.yaml
_progress "grep traefik-internet container"
grep -Fq 'container_name: llm-studio-traefik-internet' compose.yaml
_progress "grep profiles local"
grep -Fq 'profiles: ["local"]' compose.yaml
_progress "grep profiles internet"
grep -Fq 'profiles: ["internet"]' compose.yaml
_progress "grep certResolver letsencrypt"
grep -Fq 'certResolver: letsencrypt' configs/traefik/dynamic/llm-studio.internet.yml.template
_progress "grep LLM_STUDIO_TRAEFIK_MODE=local"
grep -Fq 'LLM_STUDIO_TRAEFIK_MODE=local' .env.example
_progress "grep traefik.yml mount"
grep -Fq './configs/traefik/traefik.yml:/etc/traefik/traefik.yml:ro' compose.yaml
_progress "grep api:8000 traefik dynamic"
grep -Fq 'url: "http://api:8000"' configs/traefik/dynamic/llm-studio.yml
_progress "grep install_docker hint"
grep -Fq 'Docker is not installed; run sudo ./scripts/install_docker.sh' scripts/setup.sh
_progress "grep download.docker.com"
grep -Fq 'download.docker.com/linux/' scripts/install_docker.sh
_progress "grep BACKUP_COMPLETE"
grep -Fq 'BACKUP_COMPLETE' scripts/backup_data.sh scripts/restore_data.sh
_progress "grep sha256sum check"
grep -Fq 'sha256sum --check SHA256SUMS' scripts/restore_data.sh
_progress "grep first_token_latency_ms"
grep -Fq 'first_token_latency_ms' api/model_runtime.py api/app.py
_progress "grep cache_hit_percent"
grep -Fq 'cache_hit_percent' api/app.py
_progress "grep source_ip"
grep -Fq 'source_ip' api/tracing.py
_progress "grep x-session-affinity"
grep -Fq 'x-session-affinity' api/tracing.py
_progress "grep model_loaded"
grep -Fq 'model_loaded' api/model_runtime.py
_progress "grep model_unloaded"
grep -Fq 'model_unloaded' api/model_runtime.py
_progress "grep resident_seconds"
grep -Fq 'resident_seconds' api/model_runtime.py
_progress "grep observability profile"
grep -Fq 'profiles: ["observability"]' compose.yaml
_progress "grep openobserve image"
grep -Fq 'public.ecr.aws/zinclabs/openobserve:v1.0.3' compose.yaml .env.example
_progress "grep otel collector image"
grep -Fq 'otel/opentelemetry-collector-contrib:0.153.0' compose.yaml .env.example
_progress "grep llm_studio_requests"
grep -Fq 'llm_studio_requests' configs/otel-collector.yml
_progress "grep web_search tool_choice required"
grep -Fq 'tool_choice": "required"' test/scripts/web_search_contract.py
_progress "grep LLM_STUDIO_API_CPUS=3.0"
grep -Fq 'LLM_STUDIO_API_CPUS=3.0' .env.example
_progress "grep LLM_STUDIO_CPU_THREADS=3"
grep -Fq 'LLM_STUDIO_CPU_THREADS=3' .env.example

_progress "no application rate limiter"
if rg -n 'SlidingWindowRateLimiter|rate_limiter|RATE_LIMIT_PER_MINUTE' api scripts .env.example compose.yaml; then
  printf 'Rate-limit removal check failed: application limiter references remain.\n' >&2
  exit 1
fi

_progress "no docker.sock / hermes attachment"
if grep -Eq '/var/run/docker.sock|hermes.*(volume|network)' compose.yaml configs/traefik/traefik.yml configs/traefik/dynamic/llm-studio.yml; then
  printf 'Isolation check failed: prohibited Docker socket or Hermes attachment found.\n' >&2
  exit 1
fi

_progress "no AI_LAB legacy names"
if rg -i --no-ignore 'AI_LAB|ai-lab|ai_lab|ai\.lab|AI[ -]lab' \
  --glob '!.git/**' --glob '!.agents/**' --glob '!.codex/**' \
  --glob '!test/run.sh' .; then
  printf 'Naming check failed: legacy project identifiers remain.\n' >&2
  exit 1
fi

_progress "docker compose config --quiet"
test_env="$(mktemp)"
trap 'rm -f -- "${test_env}"; find api -type d -name __pycache__ -prune -exec rm -rf {} +' EXIT
sed \
  -e 's|LLM_STUDIO_DATA_DIR=/opt/data/llm-studio|LLM_STUDIO_DATA_DIR=/tmp/llm-studio-test|' \
  -e 's|replace-with-at-least-32-random-characters|0123456789abcdef0123456789abcdef|' \
  .env.example >"${test_env}"

docker compose --project-name llm-studio-test --env-file "${test_env}" --file compose.yaml config --quiet

printf 'Static tests passed (%s/%s). No container was started and no model was downloaded.\n' \
  "${case_n}" "${CASE_TOTAL}"
