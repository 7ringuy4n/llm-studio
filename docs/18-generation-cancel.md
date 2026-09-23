# Generation cancel (Stop / disconnect)

## Problem

Pressing **Stop** in DeepSeek Harness (or aborting a curl/fetch) used to end
only the client wait. The VPS llm-studio worker kept generating for the loaded
model until EOS / `max_tokens`, holding the concurrency slot and burning CPU.

## Behavior now

1. Each `/v1/chat/completions` registers a cancel token under
   `X-Request-ID` / `X-Correlation-ID` / `X-Session-ID`.
2. A disconnect watcher polls `request.is_disconnected()`. On disconnect it
   sets the token and calls best-effort `model.interrupt()` (GGUF when present).
3. Hugging Face backends stop via `StoppingCriteria`; GGUF backends raise
   `GenerationCancelled` from a logits processor.
4. Cancelled generations return **HTTP 499** with
   `{"error":{"type":"cancelled_error",...}}`.
5. Request timeouts also set the cancel token (cooperative stop), then keep the
   slot reserved until the worker exits.

## Explicit cancel API

```bash
curl -sS -X POST "http://10.8.0.1:18080/v1/generation/cancel" \
  -H "Authorization: Bearer $LLM_STUDIO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"correlation_id":"<same-as-chat>"}'
```

Body fields (any one) or matching headers: `correlation_id`, `request_id`,
`session_id`. Response: `{"cancelled": true|false, "matched_id": "..."}`.

## DSH guidance

- Prefer Stop that **aborts the HTTP request** so disconnect cancel fires.
- Always send a stable `X-Correlation-ID` on chat so an explicit cancel can
  target the same job if needed.
- **Observed gap (2026-09-23):** DSH Web Stop cleared the UI but left the
  upstream `/v1/chat/completions` running to completion (~2m, HTTP 200).
  Until DSH aborts the fetch or calls `POST /v1/generation/cancel`, use the
  cancel API manually with the chat correlation id.
- After deploy, verify: start a long prompt, call cancel (or abort HTTP),
  confirm API returns 499 and CPU drops; OpenObserve shows
  `model_response_cancelled` / `model_generation_cancel_requested`.

## Tests

`python3 test/scripts/cancellation_unit.py` (also in `./test/run_all.sh`).
