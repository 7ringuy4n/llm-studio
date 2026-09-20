# Private Qwen3 LLM Studio API Setup

This repository contains the setup layer for a CPU-only Qwen3 learning lab on
an Ubuntu VPS. It exposes a small OpenAI-compatible REST surface while remaining
isolated from an existing Hermes installation.

For the hands-on learning sequence, start with the
[AI Model Training Handbook](docs/README.md).

The configured upstream model identifier is
[`Qwen/Qwen3-0.6B`](https://huggingface.co/Qwen/Qwen3-0.6B), as published by
Qwen. This setup provides inference and a secure service boundary; the larger
training and RAG curriculum described in `prompt.md` remains a separate phase.

## Safety model

- The environment is inspected and recorded before setup changes anything.
- The Compose project is named `llm-studio` and uses only `llm-studio-net`.
- No Hermes network, volume, path, database, or Docker socket is attached.
- The host port binds to `127.0.0.1` by default. An explicit private/OpenVPN IP
  is accepted; wildcard and public IP bindings are refused.
- Every `/v1/*` request requires a constant-time checked Bearer API key.
- The key is generated with OpenSSL, kept in `.env` with mode `0600`, omitted
  from logs, and never printed by setup.
- The API runs as a non-root user with a read-only root filesystem, all Linux
  capabilities dropped, `no-new-privileges`, bounded PID/CPU/RAM use, one
  generation worker, request validation, rate limits, and a generation timeout.
- Docker log rotation is enabled and prompts/responses are not logged.
- OpenVPN provides encrypted transport. Do not route the API port publicly.

Users who can administer Docker can inspect container environment variables and
therefore have equivalent access to the API key. Docker administrator access is
root-equivalent and must remain restricted.

## Prerequisites

- Ubuntu 22.04 or 24.04
- Docker Engine and Docker Compose v2 already installed
- `curl`, `openssl`, Python 3, `ip`, and `ss`
- approximately 4 vCPU, 16 GB RAM, and at least 10 GB free disk
- working OpenVPN if access is needed from another machine

The script deliberately does not install or reconfigure Docker or OpenVPN.

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

This is OpenAI chat-completions compatibility, not the Anthropic Messages API.
Tool calls, image inputs, audio, batches, assistants, and file APIs are not
implemented. Streaming is response-framed after generation rather than true
token-by-token streaming.

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
  --data '{"model":"Qwen/Qwen3-0.6B","messages":[{"role":"user","content":"Explain LoRA briefly."}],"max_tokens":128,"temperature":0}' \
  "${OPENAI_BASE_URL}/chat/completions"
```

Coding clients that support a custom OpenAI-compatible base URL can use those
two environment variables. Client-specific features that require tool calling
will not work with this minimal endpoint.

The model downloads lazily on the first chat request and is cached under
`/opt/data/llm-studio/models` by default. On CPU, that first request can take several
minutes. Health and model-discovery checks do not trigger the download.

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

Qwen3-0.6B is suitable for learning, classification, and small experiments. It
is not comparable to a large production coding model. CPU generation will be
slow, the in-memory rate limiter resets with the single API process, and a timed
out PyTorch generation cannot safely be killed mid-thread. The concurrency slot
remains reserved until that work actually ends, preventing timed-out jobs from
piling up. For production traffic, use a dedicated model server and a durable
gateway-level rate limiter.
