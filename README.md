# Private Multi-model LLM Studio API Setup

This repository contains the setup layer for a CPU-only Qwen3.5 multimodal learning lab on
an Ubuntu VPS. It exposes a small OpenAI-compatible REST surface while remaining
isolated from an existing Hermes installation.

For the hands-on learning sequence, start with the
[AI Model Training Handbook](docs/README.md).

The configured upstream model identifier is
[`Qwen/Qwen3.5-0.8B`](https://huggingface.co/Qwen/Qwen3.5-0.8B), as published by
Qwen. This setup provides inference and a secure service boundary; the larger
training and RAG curriculum described in `prompt.md` remains a separate phase.

## Safety model

- The environment is inspected and recorded before setup changes anything.
- The Compose project is named `llm-studio` and uses only `llm-studio-net`.
- A dedicated mode-specific LLM Studio Traefik proxy owns the listener. It uses only a
  read-only file provider, has no Docker socket, and cannot discover Hermes.
- No Hermes network, volume, path, database, or Docker socket is attached.
- The host port binds to `127.0.0.1` by default. An explicit private/OpenVPN IP
  is accepted; wildcard and public IP bindings are refused.
- Every `/v1/*` request requires a constant-time checked Bearer API key.
- The key is generated with OpenSSL, kept in `.env` with mode `0600`, omitted
  from logs, and never printed by setup.
- The API runs as a non-root user with a read-only root filesystem, all Linux
  capabilities dropped, `no-new-privileges`, bounded PID/CPU use, one
  generation worker, request validation, and a generation timeout.
- Compose does not impose a RAM ceiling. Only one model is resident and it is
  unloaded after one idle hour; size the host for the selected model and cache.
- Docker log rotation is enabled. Structured request tracing records prompt and
  response text in the protected data directory; image payloads and API keys are
  excluded. Disable it with `LLM_STUDIO_REQUEST_TRACE_LOGGING=false` if needed.
- Local mode supports loopback/private/OpenVPN transport. Internet mode exposes
  API-key-protected HTTPS using a dedicated Let's Encrypt Traefik profile.
- Optional OpenObserve/OTel services have unique names, storage, and a private
  listener; they do not mount the Docker socket or join Hermes resources.

Users who can administer Docker can inspect container environment variables and
therefore have equivalent access to the API key. Docker administrator access is
root-equivalent and must remain restricted.

## Prerequisites

- Ubuntu 22.04 or 24.04
- Docker Engine and Docker Compose v2, or sudo permission to install them
- `curl`, `openssl`, Python 3, `ip`, and `ss`
- approximately 4 vCPU, 16 GB RAM, and at least 10 GB free disk
- working OpenVPN if access is needed from another machine

For a server without Docker, follow
[Clean Ubuntu setup with isolated Traefik](docs/11-clean-ubuntu-traefik-setup.md).
For moving trained data or rebuilding a host, follow
[Backup, restore, and clean-OS migration](docs/12-backup-restore-migration.md).
For end-to-end request, token, cache, latency, IP, and resource monitoring, see
[Request tracing and the OpenObserve UI](docs/13-observability.md).
The Docker bootstrap does not change daemon settings, firewall rules, OpenVPN,
or existing Compose stacks.

## Setup

First run the static checks on the project files:

```bash
make test
```

Run the idempotent setup on the target VPS:

```bash
sudo make setup
```

The default data root is `/opt/data/llm-studio`. Setup creates only this subtree,
builds only `llm-studio-api:local`, starts only the `llm-studio` Compose project, and
runs authentication smoke tests. Running it again preserves models and data.

To bind directly to an OpenVPN interface, first obtain its exact address with
`ip addr`, then run:

```bash
sudo LLM_STUDIO_BIND_ADDRESS=10.8.0.1 LLM_STUDIO_PORT=18080 make setup
```

The script refuses `0.0.0.0`, `::`, public IP addresses, an address not assigned
to the host, a conflicting port, or an existing `llm-studio-net` it does not own.

To inspect and validate without building or starting containers:

```bash
sudo make validate
```

Review [docs/environment.md](docs/environment.md) after either command. The
report excludes container environment variables so it does not collect secrets.

## REST API

The supported compatibility surface is:

- `GET /health` — unauthenticated, returns no secret or model content
- `GET /v1/models` — authenticated model discovery
- `POST /v1/chat/completions` — authenticated chat completion, including SSE
  responses when `stream: true`

This is a focused OpenAI chat-completions compatibility surface. Text, image
inputs, and function tool calls are supported. Audio, video, batches,
assistants, and file APIs are not implemented. Streaming is response-framed
after generation rather than true token-by-token streaming.
Every response carries request/session/correlation/trace/span/execution IDs.
Chat responses also expose `Server-Timing`, `X-First-Token-Ms`,
`X-Last-Token-Ms`, `X-Input-Tokens`, `X-Output-Tokens`, and
`X-Cache-Hit-Percent`.

For security, image input must be an embedded PNG, JPEG, or WebP data URL.
Remote URLs and local file paths are rejected, preventing the API from becoming
an SSRF or local-file proxy. A request may contain at most two images, each no
larger than 3 MiB decoded and 2048 pixels on either side.

Read the generated key without placing it in shell history:

```bash
set -a
source ./.env
set +a
export OPENAI_API_KEY="${LLM_STUDIO_API_KEY}"
export OPENAI_BASE_URL="http://${LLM_STUDIO_BIND_ADDRESS}:${LLM_STUDIO_PORT}/v1"
```

Then call the standard endpoints:

```bash
curl --fail-with-body \
  --header "Authorization: Bearer ${OPENAI_API_KEY}" \
  "${OPENAI_BASE_URL}/models"
```

```bash
curl --fail-with-body \
  --header "Authorization: Bearer ${OPENAI_API_KEY}" \
  --header 'Content-Type: application/json' \
  --data '{"model":"Qwen/Qwen3.5-0.8B","messages":[{"role":"user","content":"Explain LoRA briefly."}],"max_tokens":128,"temperature":0}' \
  "${OPENAI_BASE_URL}/chat/completions"
```

Qwen3.5 reasoning mode is opt-in with `enable_thinking`,
`chat_template_kwargs.enable_thinking`, or a non-off `reasoning_effort` value:

```bash
curl --fail-with-body \
  --header "Authorization: Bearer ${OPENAI_API_KEY}" \
  --header 'Content-Type: application/json' \
  --data '{"model":"Qwen/Qwen3.5-0.8B","messages":[{"role":"user","content":"Which is larger: 9.11 or 9.9? Explain."}],"enable_thinking":true,"max_tokens":512,"temperature":1.0,"top_p":0.95,"top_k":20,"min_p":0.0}' \
  "${OPENAI_BASE_URL}/chat/completions"
```

`reasoning_effort=off` disables thinking. `low`, `medium`, `high`, `xhigh`, and
`max` enable thinking, but Qwen3.5 does not assign distinct compute budgets to
those labels. Thinking tokens share the `max_tokens` budget with the final answer. Qwen
warns that the 0.8B checkpoint can enter long thinking loops, so use a bounded
budget and timeout. Reasoning is returned separately as `reasoning_content`.

## Multimodal image request

Send an embedded data URL through an OpenAI-compatible `image_url` content part:

```json
{
  "model": "Qwen/Qwen3.5-0.8B",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
      {"type": "text", "text": "Describe this image concisely."}
    ]
  }],
  "max_tokens": 160,
  "temperature": 0.7,
  "top_p": 0.8,
  "top_k": 20
}
```

The Postman environment contains a runnable sample in `sampleImageDataUrl`.
Keep images small on this CPU-only VPS; vision preprocessing and generation are
substantially slower than short text requests.

Coding clients that support a custom OpenAI-compatible base URL can use those
two environment variables. The endpoint accepts OpenAI-style `tools`, assistant
`tool_calls`, and `tool` result messages, and translates Qwen native function
calls back into the OpenAI response shape.

For DeepSeek Harness, use the OpenAI completions adapter and disable optional
fields that this small local endpoint does not need:

```yaml
displayName: homelab
apiKeyEnv: HOMELAB_API_KEY
api: openai-completions
baseURL: http://10.8.0.1:18080/v1
compat:
  supportsDeveloperRole: false
  supportsStore: false
  supportsReasoningEffort: true
  supportsUsageInStreaming: true
  maxTokensField: max_tokens
  thinkingFormat: qwen
models:
  - id: Qwen/Qwen3.5-0.8B
    name: Qwen/Qwen3.5-0.8B
    contextWindow: 262144
    maxTokens: 512
    input: [text, image]
    reasoningEfforts:
      "off": null
      low: low
      medium: medium
      high: high
      xhigh: xhigh
      max: max
  - id: Qwen/Qwen3.5-2B
    name: Qwen3.5 2B
    contextWindow: 262144
    maxTokens: 512
    input: [text, image]
    reasoningEfforts:
      "off": null
      low: low
      medium: medium
      high: high
      xhigh: xhigh
      max: max
```

Set `HOMELAB_API_KEY` to the value of `LLM_STUDIO_API_KEY` from the server
root-owned `.env`; do not put the key in the YAML file or commit it.

Model weights are cached under `/opt/data/llm-studio/models`. Setup preloads the
0.8B and 2B Qwen3.5 checkpoints. Only one model is resident in RAM: requesting a
different model unloads the current one before loading the selected model. After
`MODEL_IDLE_UNLOAD_SECONDS` without a completed generation, the resident model is
released automatically. The default is one hour (`3600` seconds). Set the timeout
to `0` to disable idle unloading.

Use the model manager instead of editing cache paths manually:

```bash
make models
make model-install MODEL=qwen35-2b
make model-activate MODEL=qwen35-2b
make model-remove MODEL=qwen35-2b
make model-remove MODEL=qwen35-2b FORCE=1  # stops API if this is active
```

Removing a model also removes it from `MODEL_ALLOWED_MODELS`, preventing an
automatic re-download on the next request. `model-activate` installs and enables
it again. Cache deletion briefly stops the API so no dynamically selected model
still has the deleted files memory-mapped.

The catalog also includes `qwen3-1.7b`, which is text-only. There is no official
`Qwen/Qwen3.5-1.7B`; use `qwen35-2b` when Qwen3.5 vision is required.

Larger CPU models use Q4_K_M GGUF weights so they remain practical on a VPS:

| Alias | API model ID | Download size | Capability |
| --- | --- | ---: | --- |
| `qwen3-8b` | `Qwen/Qwen3-8B` | about 5.0 GB | text, reasoning |
| `deepseek-r1-7b` | `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` | about 4.7 GB | text, reasoning |
| `llama31-8b` | `meta-llama/Llama-3.1-8B-Instruct` | about 4.9 GB | text |

These are opt-in and are not downloaded by setup. Install one with
`make model-install MODEL=<alias>`, then enable it with
`make model-activate MODEL=<alias>`. Q4_K_M avoids the 15-16 GB BF16 weight
footprint while keeping a balanced quality/size tradeoff.

The relevant `.env` controls are:

```dotenv
MODEL_ID=Qwen/Qwen3.5-0.8B
MODEL_BACKEND=multimodal
MODEL_DTYPE=auto
MODEL_REVISION=main
MODEL_ALLOWED_MODELS=Qwen/Qwen3.5-0.8B,Qwen/Qwen3.5-2B
MODEL_PRELOAD_MODELS=qwen35-0.8b,qwen35-2b
MODEL_IDLE_UNLOAD_SECONDS=3600
MODEL_GGUF_CONTEXT_TOKENS=32768
MODEL_KV_CACHE_BYTES=2147483648
MODEL_CONTEXT_TOKENS=262144
MODEL_MAX_INPUT_TOKENS=262144
MODEL_MAX_NEW_TOKENS=2048
LLM_STUDIO_REQUEST_TIMEOUT_SECONDS=900
LLM_STUDIO_QUEUE_TIMEOUT_SECONDS=900
```

There is no Docker memory ceiling in `compose.yaml`; Docker can use newly added
host RAM without a Compose change. `MODEL_GGUF_CONTEXT_TOKENS` is the operational
GGUF context allocation and can be raised after a RAM upgrade, up to each model's
native context. `MODEL_KV_CACHE_BYTES` controls the cross-request llama.cpp RAM
prompt cache. Transformer models keep generation-local KV caching; GGUF models
also reuse matching prompt prefixes between requests while the model remains
loaded. Model unload clears both caches.

The API has no requests-per-minute limiter. Because one CPU model generation runs
at a time, extra coding-agent calls wait in a FIFO-style semaphore queue for up to
`LLM_STUDIO_QUEUE_TIMEOUT_SECONDS` instead of being rejected immediately with
429. Increase CPU/concurrency only after load testing the host.

Use `MODEL_BACKEND=multimodal` for models loaded by Transformers'
`AutoModelForMultimodalLM`, or `MODEL_BACKEND=causal-lm` for ordinary text-only
chat models loaded by `AutoModelForCausalLM`. Set the context and generation
limits to the selected model's published values. The API reserves requested
completion tokens inside the total context window, so prompt plus completion
never exceeds its catalog context limit.

DSH web search is not supplied by the language model. The DSH web profile must
enable its `tool-web` plugin and configure a search provider. The bundled
`deepseek-official` provider requires a separate `DEEPSEEK_API_KEY`; the homelab
inference key cannot substitute for it. HTTP fetch and web search are also
separate capabilities.

## Operations

```text
make status       service health and state
make logs         API operational logs; prompts are excluded
make resources    CPU, memory, disk, and container use
make smoke        authentication and discovery checks
make smoke-model  download/load Qwen and verify one short generation
make stop         stop the API without deleting data
make start        start the existing API configuration
make rotate-key   invalidate the old key and recreate only the API container
```

`make stop` does not remove the container, network, image, or data. There is no
prune, recursive delete, network modification, volume deletion, or OpenVPN
modification command in this project.

## Current limits

Qwen3.5-0.8B is suitable for learning, classification, and small experiments. It
is not comparable to a large production coding model. CPU generation will be
slow, and a timed out PyTorch generation cannot safely be killed mid-thread. The concurrency slot
remains reserved until that work actually ends, preventing timed-out jobs from
piling up. The API has no request-per-minute limiter; keep it VPN-only. For production
traffic, use a dedicated model server and a durable gateway-level rate limiter.
