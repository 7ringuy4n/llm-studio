from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.encoders import jsonable_encoder

from .model_runtime import GenerationResult, runtime
from .schemas import ChatCompletionRequest
from .security import require_api_key
from .settings import settings

MAX_REQUEST_BYTES = 64 * 1024
logger = logging.getLogger("llm_studio_api")
logging.basicConfig(level=logging.INFO, format="%(message)s")
generation_slots = asyncio.Semaphore(settings.max_concurrent_requests)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.model_load_on_start:
        await asyncio.to_thread(runtime.load)
    yield


app = FastAPI(
    title="LLM Studio Qwen API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_and_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex}"
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"error": {"message": "Request body is too large", "type": "invalid_request_error"}},
                    headers={"X-Request-ID": request_id},
                )
        except ValueError:
            return JSONResponse(status_code=400, content={"error": {"message": "Invalid Content-Length"}})

    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        json.dumps(
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }
        )
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": {"message": "Request validation failed", "type": "invalid_request_error", "details": jsonable_encoder(exc.errors())}},
    )


@app.get("/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "model_loaded": runtime.loaded}


@app.get("/v1/models")
async def models(_: str = Depends(require_api_key)) -> dict[str, object]:
    return {
        "object": "list",
        "data": [
            {
                "id": settings.model_id,
                "object": "model",
                "created": 0,
                "owned_by": "llm-studio",
            }
        ],
    }


def _completion_payload(
    completion_id: str, created: int, request: ChatCompletionRequest, result: GenerationResult
) -> dict[str, object]:
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": result.prompt_tokens,
            "completion_tokens": result.completion_tokens,
            "total_tokens": result.prompt_tokens + result.completion_tokens,
        },
    }


async def _sse(payload: dict[str, object]):
    choice = payload["choices"][0]
    chunk = {
        "id": payload["id"],
        "object": "chat.completion.chunk",
        "created": payload["created"],
        "model": payload["model"],
        "choices": [
            {
                "index": 0,
                "delta": choice["message"],
                "finish_reason": None,
            }
        ],
    }
    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    final = {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
    yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    _: str = Depends(require_api_key),
):
    if request.model not in {settings.model_id, "qwen3-0.6b"}:
        raise HTTPException(status_code=404, detail="Requested model is not available")
    if request.max_tokens and request.max_tokens > settings.max_new_tokens:
        raise HTTPException(
            status_code=400,
            detail=f"max_tokens cannot exceed {settings.max_new_tokens}",
        )

    try:
        await asyncio.wait_for(generation_slots.acquire(), timeout=0.1)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=429,
            detail="The model is busy; retry later",
            headers={"Retry-After": "5"},
        ) from exc
    generation_task = asyncio.create_task(asyncio.to_thread(runtime.generate, request))
    release_slot_now = True
    try:
        result = await asyncio.wait_for(
            asyncio.shield(generation_task),
            timeout=settings.request_timeout_seconds,
        )
    except TimeoutError as exc:
        # A Python worker thread cannot be killed safely. Keep its concurrency slot
        # reserved until it really exits so timed-out work cannot pile up.
        release_slot_now = False
        generation_task.add_done_callback(lambda _: generation_slots.release())
        raise HTTPException(status_code=504, detail="Generation timed out") from exc
    except (OSError, RuntimeError) as exc:
        logger.exception("Model generation failed")
        raise HTTPException(status_code=503, detail="Model is unavailable") from exc
    finally:
        if release_slot_now:
            generation_slots.release()

    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    payload = _completion_payload(completion_id, int(time.time()), request, result)
    if request.stream:
        return StreamingResponse(_sse(payload), media_type="text/event-stream")
    return payload
