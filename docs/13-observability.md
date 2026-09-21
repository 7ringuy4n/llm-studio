# Request tracing and the OpenObserve UI

LLM Studio writes one structured JSONL event stream and can optionally ship it,
together with host CPU/RAM/load/network/process metrics, to a private
OpenObserve UI. Observability is disabled by default and is not routed through
the public API Traefik.

## Why OpenObserve

The selection was reviewed on 2026-09-21. OpenObserve had roughly 22,000 GitHub
stars, ships as one application binary/container, supports logs, metrics,
traces, dashboards, and LLM observability, and accepts native OTLP. Langfuse
had more stars and deeper prompt/evaluation workflows, but its self-hosted stack
is heavier and does not replace host-resource monitoring. Grafana plus Loki and
Tempo is mature but adds several services. Phoenix is strong for model tracing
and evaluation but is not as complete for host metrics. OpenObserve therefore
fits this single-VPS deployment best.

The deployment pins OpenObserve `v1.0.3` and OpenTelemetry Collector Contrib
`0.153.0`; do not switch to floating `latest` tags. Upstream references:

- <https://github.com/openobserve/openobserve>
- <https://openobserve.ai/docs/ingestion/logs/otlp/>
- <https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/filelogreceiver>
- <https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/receiver/hostmetricsreceiver>

## Enable the UI

After normal setup:

```bash
make observability-up
```

The command creates a random OpenObserve password when needed, stores it only
in `.env` (mode `0600`) with all character classes required by OpenObserve, and
opens the UI on `127.0.0.1:15080`. Read the login
without copying it into shell history:

```bash
sudo awk -F= '/^LLM_STUDIO_OPENOBSERVE_(EMAIL|PASSWORD)=/ {print $1 "=" $2}' .env
```

Open `http://127.0.0.1:15080`. From a laptop, use an SSH tunnel:

```bash
ssh -L 15080:127.0.0.1:15080 tn@your-vps
```

To expose the UI only on OpenVPN, rerun setup with the exact VPN address:

```bash
sudo LLM_STUDIO_OBSERVABILITY_ENABLED=true \
  LLM_STUDIO_OBSERVABILITY_BIND_ADDRESS=10.8.0.1 \
  ./scripts/setup.sh
```

Never bind the observability UI to `0.0.0.0` or publish it through public
Traefik. Setup rejects wildcard and public UI bind addresses.

Disable the collector and UI while preserving data:

```bash
make observability-down
```

Telemetry is retained for 30 days by default to keep the single-node disk
bounded. Change `LLM_STUDIO_OBSERVABILITY_RETENTION_DAYS` (minimum 3) in
`.env`, then recreate `openobserve`. The JSONL source also rotates at 50 MiB
with ten backups.

## What is captured

OpenObserve **Logs** stream `llm_studio_requests` contains:

- model, full text request, full text response, status, and streaming flag;
- `request_id`, `session_id`, `correlation_id`, `trace_id`, `span_id`, and
  `execution_id`;
- `source_ip`, direct `peer_ip`, and the validated forwarded IP chain;
- queue, model, endpoint, first-token, and last-token latency in milliseconds;
- input, output, total, and cached-input tokens;
- cache-hit percentage and output tokens/second;
- process maximum RSS and accumulated user/system CPU time.

Embedded image bytes are never stored: the logger records only their character
count and SHA-256 digest. Long strings are truncated at
`LLM_STUDIO_REQUEST_TRACE_MAX_CONTENT_CHARS`. API keys and authorization
headers are never written. Text prompts and responses **are sensitive** and are
stored in `/opt/data/llm-studio/logs/requests.jsonl`; protect backups and UI
credentials accordingly.

`first_token_latency_ms` is the model's first generated-token time. Transformers
records it through a stopping callback; llama.cpp records it through the
sampling/logits callback without changing logits. `last_token_latency_ms` is
the final sampling-callback time. The
HTTP SSE adapter currently frames the completed result after generation, so
these are model timings, not browser-visible streaming TTFT.

For Transformers models, the KV cache is request-scoped and
`cached_input_tokens` is normally zero. For GGUF models, llama.cpp can reuse a
prompt prefix across requests and reports cached tokens when its backend
provides them; this service also records the matched RAM-cache prefix directly
for the pinned backend. A zero cache-hit percentage is valid and must not be
inferred from response speed alone.

## Find one request end to end

1. Copy `X-Trace-ID`, `X-Request-ID`, or `X-Session-ID` from Postman/DSH.
2. In OpenObserve, choose **Logs** and stream `llm_studio_requests`.
3. Filter on the matching field.
4. Compare `model_request_received`, `model_response_completed`, and
   `http_request_completed` for the same IDs.
5. Inspect queue/model/first-token/last-token/endpoint latency, token counts,
   cache fields, response, and source IP.

Use `model` to see traffic for every installed/selected model, `session_id` to
follow a conversation, `correlation_id` to group a batch, and `execution_id` to
identify a single generation attempt. Host metrics appear in OpenObserve's
Metrics explorer with `service.name=llm-studio-host`.

## Useful checks

```bash
make observability-logs
tail -f /opt/data/llm-studio/logs/requests.jsonl
docker compose --profile observability ps
```

Run **Chat Completion**, **KV Cache**, and **Concurrent Batch** in Postman. The
tests verify first/last-token headers, cache percentage, input/output tokens,
shared session/correlation/trace IDs, unique request/span/execution IDs, and
successful queued concurrent requests.
