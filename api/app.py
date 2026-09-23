from __future__ import annotations

import asyncio
import json
import logging
import resource
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder

from .cancellation import CancelToken, GenerationCancelled, cancel_registry
from .model_runtime import ALLOWED_BY_ID, ALLOWED_MODELS, GenerationResult, runtime
from .schemas import CancelGenerationRequest, ChatCompletionRequest
from .security import require_api_key
from .settings import settings
from .tracing import new_trace_context, response_headers, trace_event

MAX_REQUEST_BYTES = 16 * 1024 * 1024
logger = logging.getLogger("llm_studio_api")
logging.basicConfig(level=logging.INFO, format="%(message)s")
generation_slots = asyncio.Semaphore(settings.max_concurrent_requests)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.model_load_on_start:
        await asyncio.to_thread(runtime.load, settings.model_id, "startup")
    try:
        yield
    finally:
        await asyncio.to_thread(runtime.unload, "shutdown")


app = FastAPI(
    title="LLM Studio Multi-model API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_and_request_id(request: Request, call_next):
    trace = new_trace_context(
        request.headers,
        request.client.host if request.client is not None else None,
    )
    request.state.trace = trace
    content_length = request.headers.get("content-length")
    response = None
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                response = JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"error": {"message": "Request body is too large", "type": "invalid_request_error"}},
                )
        except ValueError:
            response = JSONResponse(status_code=400, content={"error": {"message": "Invalid Content-Length"}})

    started = time.monotonic()
    if response is None:
        response = await call_next(request)
    duration_ms = round((time.monotonic() - started) * 1000, 1)
    for name, value in response_headers(trace).items():
        response.headers[name] = value
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers.setdefault("Server-Timing", f"total;dur={duration_ms}")
    if request.url.path == "/v1/chat/completions":
        response.headers.setdefault("X-KV-Cache", "enabled; scope=generation")
    logger.info(
        json.dumps(
            {
                "request_id": trace.request_id,
                "session_id": trace.session_id,
                "correlation_id": trace.correlation_id,
                "trace_id": trace.trace_id,
                "span_id": trace.span_id,
                "execution_id": trace.execution_id,
                "source_ip": trace.source_ip,
                "peer_ip": trace.peer_ip,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            }
        )
    )
    trace_event(
        "http_request_completed",
        trace,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        total_latency_ms=duration_ms,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    trace = getattr(request.state, "trace", None)
    if trace is not None:
        trace_event(
            "request_validation_failed",
            trace,
            method=request.method,
            path=request.url.path,
            status=422,
            error={
                "type": "invalid_request_error",
                "details": jsonable_encoder(exc.errors()),
            },
        )
    return JSONResponse(
        status_code=422,
        content={"error": {"message": "Request validation failed", "type": "invalid_request_error", "details": jsonable_encoder(exc.errors())}},
    )


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "model_loaded": runtime.loaded,
        "loaded_model": runtime.loaded_model_id,
    }


@app.post("/v1/generation/cancel")
async def cancel_generation(
    body: CancelGenerationRequest,
    raw_request: Request,
    _: str = Depends(require_api_key),
) -> dict[str, object]:
    """Abort an in-flight generation by correlation / request / session id.

    DeepSeek Harness Stop should also abort the HTTP chat request (disconnect).
    Use this endpoint when the client keeps the socket open but still wants the
    VPS worker to stop (pass the same X-Correlation-ID used for chat).
    """
    trace = raw_request.state.trace
    candidates = [
        body.correlation_id,
        body.request_id,
        body.session_id,
        raw_request.headers.get("x-correlation-id"),
        raw_request.headers.get("x-request-id"),
        raw_request.headers.get("x-session-id"),
    ]
    cancelled = False
    matched: str | None = None
    for key in candidates:
        if key and cancel_registry.cancel(key):
            cancelled = True
            matched = key
            break
    if cancelled:
        runtime.request_interrupt()
    elif not any(candidates):
        raise HTTPException(
            status_code=400,
            detail="provide correlation_id, request_id, or session_id (body or headers)",
        )
    trace_event(
        "model_generation_cancel_requested",
        trace,
        cancelled=cancelled,
        matched_id=matched,
        reason="explicit_cancel_api",
    )
    return {"cancelled": cancelled, "matched_id": matched}


@app.get("/v1/models")
async def models(raw_request: Request, _: str = Depends(require_api_key)) -> dict[str, object]:
    payload = {
        "object": "list",
        "data": [
            {
                "id": model.id,
                "object": "model",
                "created": 0,
                "owned_by": "llm-studio",
                "input_modalities": ["text", "image"] if model.vision else ["text"],
                "supports_reasoning": model.reasoning,
            }
            for model in ALLOWED_MODELS
        ],
    }
    trace_event("model_catalog_returned", raw_request.state.trace, response=payload)
    return payload


def _completion_payload(
    completion_id: str, created: int, request: ChatCompletionRequest, result: GenerationResult
) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "content": result.text}
    if result.reasoning is not None:
        message["reasoning_content"] = result.reasoning
    finish_reason = "stop"
    if result.tool_calls:
        finish_reason = "tool_calls"
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in result.tool_calls
        ]
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.prompt_tokens + result.completion_tokens,
            "prompt_tokens_details": {
                "cached_tokens": result.cached_prompt_tokens,
            },
        },
    }


async def _sse(payload: dict[str, object], include_usage: bool):
    choice = payload["choices"][0]
    message = dict(choice["message"])
    reasoning = message.pop("reasoning_content", None)
    if reasoning is not None:
        reasoning_chunk = {
            "id": payload["id"],
            "object": "chat.completion.chunk",
            "created": payload["created"],
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "reasoning_content": reasoning},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(reasoning_chunk, ensure_ascii=False)}\n\n"
    if reasoning is not None:
        message.pop("role", None)
    chunk = {
        "id": payload["id"],
        "object": "chat.completion.chunk",
        "created": payload["created"],
        "model": payload["model"],
        "choices": [
            {
                "index": 0,
                "delta": message,
                "finish_reason": None,
            }
        ],
    }
    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    final = {
        **chunk,
        "choices": [
            {"index": 0, "delta": {}, "finish_reason": choice["finish_reason"]}
        ],
    }
    yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
    if include_usage:
        usage = {**chunk, "choices": [], "usage": payload["usage"]}
        yield f"data: {json.dumps(usage, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    raw_request: Request,
    _: str = Depends(require_api_key),
):
    trace = raw_request.state.trace
    endpoint_started = time.monotonic()
    trace_event(
        "model_request_received",
        trace,
        model=request.model,
        stream=request.stream,
        request=request.model_dump(exclude_none=True),
    )
    if request.model not in ALLOWED_BY_ID:
        trace_event(
            "model_response_failed",
            trace,
            model=request.model,
            status=404,
            error="Requested model is not available",
        )
        raise HTTPException(status_code=404, detail="Requested model is not available")
    model_spec = ALLOWED_BY_ID[request.model]
    maximum_completion = min(settings.max_new_tokens, model_spec.max_new_tokens)
    if request.requested_max_tokens and request.requested_max_tokens > maximum_completion:
        trace_event(
            "model_response_failed",
            trace,
            model=request.model,
            status=400,
            error=f"requested completion tokens cannot exceed {maximum_completion}",
        )
        raise HTTPException(
            status_code=400,
            detail=f"requested completion tokens cannot exceed {maximum_completion}",
        )

    queue_started = time.monotonic()
    try:
        await asyncio.wait_for(
            generation_slots.acquire(), timeout=settings.queue_timeout_seconds
        )
    except TimeoutError as exc:
        trace_event(
            "model_response_failed",
            trace,
            model=request.model,
            status=429,
            queue_latency_ms=round((time.monotonic() - queue_started) * 1000, 1),
            error="The model is busy; retry later",
        )
        raise HTTPException(
            status_code=429,
            detail="The model is busy; retry later",
            headers={"Retry-After": "5"},
        ) from exc
    queue_latency_ms = round((time.monotonic() - queue_started) * 1000, 1)
    model_started = time.monotonic()
    cancel_token = CancelToken()
    registered_keys = cancel_registry.register(
        cancel_token,
        trace.request_id,
        trace.correlation_id,
        trace.session_id,
    )
    generation_task = asyncio.create_task(
        asyncio.to_thread(runtime.generate, request, cancel_token)
    )
    release_slot_now = True

    async def watch_client_disconnect() -> None:
        while not generation_task.done():
            if await raw_request.is_disconnected():
                cancel_token.cancel()
                runtime.request_interrupt()
                trace_event(
                    "model_generation_cancel_requested",
                    trace,
                    model=request.model,
                    reason="client_disconnected",
                )
                return
            await asyncio.sleep(0.2)

    disconnect_watcher = asyncio.create_task(watch_client_disconnect())
    try:
        result = await asyncio.wait_for(
            asyncio.shield(generation_task),
            timeout=settings.request_timeout_seconds,
        )
    except TimeoutError as exc:
        # Cooperative cancel: ask the worker to stop instead of only holding the slot.
        cancel_token.cancel()
        runtime.request_interrupt()
        release_slot_now = False

        def generation_finished(_: asyncio.Task[GenerationResult]) -> None:
            generation_slots.release()
            runtime.mark_idle()

        generation_task.add_done_callback(generation_finished)
        trace_event(
            "model_response_failed",
            trace,
            model=request.model,
            status=504,
            queue_latency_ms=queue_latency_ms,
            model_latency_ms=round((time.monotonic() - model_started) * 1000, 1),
            error="Generation timed out",
        )
        raise HTTPException(status_code=504, detail="Generation timed out") from exc
    except GenerationCancelled as exc:
        runtime.mark_idle()
        trace_event(
            "model_response_cancelled",
            trace,
            model=request.model,
            status=499,
            queue_latency_ms=queue_latency_ms,
            model_latency_ms=round((time.monotonic() - model_started) * 1000, 1),
            error=str(exc),
        )
        return JSONResponse(
            status_code=499,
            content={
                "error": {
                    "message": "Generation cancelled by client",
                    "type": "cancelled_error",
                }
            },
        )
    except asyncio.CancelledError:
        cancel_token.cancel()
        runtime.request_interrupt()
        release_slot_now = False

        def generation_finished_after_cancel(_: asyncio.Task[GenerationResult]) -> None:
            generation_slots.release()
            runtime.mark_idle()

        generation_task.add_done_callback(generation_finished_after_cancel)
        trace_event(
            "model_response_cancelled",
            trace,
            model=request.model,
            status=499,
            queue_latency_ms=queue_latency_ms,
            model_latency_ms=round((time.monotonic() - model_started) * 1000, 1),
            error="request task cancelled",
        )
        raise
    except (OSError, RuntimeError) as exc:
        runtime.mark_idle()
        logger.exception("Model generation failed")
        trace_event(
            "model_response_failed",
            trace,
            model=request.model,
            status=503,
            queue_latency_ms=queue_latency_ms,
            model_latency_ms=round((time.monotonic() - model_started) * 1000, 1),
            error=str(exc),
        )
        raise HTTPException(status_code=503, detail="Model is unavailable") from exc
    finally:
        disconnect_watcher.cancel()
        cancel_registry.unregister(*registered_keys)
        if release_slot_now:
            generation_slots.release()

    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    payload = _completion_payload(completion_id, int(time.time()), request, result)
    model_latency_ms = round((time.monotonic() - model_started) * 1000, 1)
    endpoint_latency_ms = round((time.monotonic() - endpoint_started) * 1000, 1)
    input_tokens = result.prompt_tokens
    output_tokens = result.completion_tokens
    total_tokens = input_tokens + output_tokens
    cache_hit_percent = round(
        (result.cached_prompt_tokens / input_tokens * 100) if input_tokens else 0.0, 2
    )
    generation_window_ms = result.last_token_latency_ms or model_latency_ms
    output_tokens_per_second = (
        round(output_tokens / (generation_window_ms / 1000), 3)
        if output_tokens and generation_window_ms
        else 0.0
    )
    usage = resource.getrusage(resource.RUSAGE_SELF)
    timing = (
        f"queue;dur={queue_latency_ms}, model;dur={model_latency_ms}, "
        f"first-token;dur={result.first_token_latency_ms or model_latency_ms}, "
        f"last-token;dur={result.last_token_latency_ms or model_latency_ms}, "
        f"endpoint;dur={endpoint_latency_ms}"
    )
    trace_event(
        "model_response_completed",
        trace,
        model=request.model,
        stream=request.stream,
        queue_latency_ms=queue_latency_ms,
        model_latency_ms=model_latency_ms,
        first_token_latency_ms=result.first_token_latency_ms,
        last_token_latency_ms=result.last_token_latency_ms,
        token_timing_source=result.token_timing_source,
        endpoint_latency_ms=endpoint_latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=result.cached_prompt_tokens,
        cache_hit_percent=cache_hit_percent,
        output_tokens_per_second=output_tokens_per_second,
        process_max_rss_mb=round(usage.ru_maxrss / 1024, 2),
        process_user_cpu_seconds=round(usage.ru_utime, 3),
        process_system_cpu_seconds=round(usage.ru_stime, 3),
        response=payload,
    )
    runtime.mark_idle()
    kv_cache_header = (
        "enabled; scope=prompt-and-generation"
        if model_spec.backend == "gguf"
        else "enabled; scope=generation"
    )
    metric_headers = {
        "X-KV-Cache": kv_cache_header,
        "Server-Timing": timing,
        "X-Cache-Hit-Percent": str(cache_hit_percent),
        "X-Input-Tokens": str(input_tokens),
        "X-Output-Tokens": str(output_tokens),
    }
    if result.first_token_latency_ms is not None:
        metric_headers["X-First-Token-Ms"] = str(result.first_token_latency_ms)
    if result.last_token_latency_ms is not None:
        metric_headers["X-Last-Token-Ms"] = str(result.last_token_latency_ms)
    if request.stream:
        include_usage = bool(request.stream_options and request.stream_options.include_usage)
        return StreamingResponse(
            _sse(payload, include_usage),
            media_type="text/event-stream",
            headers=metric_headers,
        )
    response.headers.update(metric_headers)
    return payload
