from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_int(name: str, default: int, *, maximum: int | None = None) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 1 or (maximum is not None and value > maximum):
        suffix = f" and <= {maximum}" if maximum is not None else ""
        raise RuntimeError(f"{name} must be >= 1{suffix}")
    return value


def _nonnegative_int(name: str, default: int, *, maximum: int | None = None) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < 0 or (maximum is not None and value > maximum):
        suffix = f" and <= {maximum}" if maximum is not None else ""
        raise RuntimeError(f"{name} must be >= 0{suffix}")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw not in {"true", "false"}:
        raise RuntimeError(f"{name} must be true or false")
    return raw == "true"


def _choice(name: str, default: str, choices: set[str]) -> str:
    value = os.getenv(name, default).strip().lower()
    if value not in choices:
        raise RuntimeError(f"{name} must be one of: {', '.join(sorted(choices))}")
    return value


@dataclass(frozen=True)
class Settings:
    api_key: str
    model_id: str
    model_backend: str
    model_dtype: str
    model_allowed_models: str
    model_idle_unload_seconds: int
    model_gguf_context_tokens: int
    model_kv_cache_bytes: int
    model_revision: str
    model_load_on_start: bool
    model_context_tokens: int
    max_input_tokens: int
    max_new_tokens: int
    min_new_tokens: int
    cpu_threads: int
    request_timeout_seconds: int
    max_concurrent_requests: int
    queue_timeout_seconds: int
    request_trace_logging: bool
    request_trace_log_path: str
    request_trace_max_content_chars: int

    @classmethod
    def from_environment(cls) -> "Settings":
        api_key = os.getenv("LLM_STUDIO_API_KEY", "")
        if len(api_key) < 32:
            raise RuntimeError("LLM_STUDIO_API_KEY must contain at least 32 characters")

        model_context_tokens = _positive_int(
            "MODEL_CONTEXT_TOKENS", 262_144, maximum=1_048_576
        )

        return cls(
            api_key=api_key,
            model_id=os.getenv("MODEL_ID", "Qwen/Qwen3.5-0.8B"),
            model_backend=_choice(
                "MODEL_BACKEND", "multimodal", {"causal-lm", "gguf", "multimodal"}
            ),
            model_dtype=_choice(
                "MODEL_DTYPE", "auto", {"auto", "bfloat16", "float16", "float32"}
            ),
            model_allowed_models=os.getenv(
                "MODEL_ALLOWED_MODELS",
                "Qwen/Qwen3.5-0.8B,Qwen/Qwen3.5-2B",
            ),
            model_idle_unload_seconds=_nonnegative_int(
                "MODEL_IDLE_UNLOAD_SECONDS", 3600, maximum=86_400
            ),
            model_gguf_context_tokens=_positive_int(
                "MODEL_GGUF_CONTEXT_TOKENS", 32768, maximum=1_048_576
            ),
            model_kv_cache_bytes=_nonnegative_int(
                "MODEL_KV_CACHE_BYTES", 2_147_483_648
            ),
            model_revision=os.getenv("MODEL_REVISION", "main"),
            model_load_on_start=_boolean("MODEL_LOAD_ON_START", False),
            model_context_tokens=model_context_tokens,
            max_input_tokens=_positive_int(
                "MODEL_MAX_INPUT_TOKENS",
                model_context_tokens,
                maximum=model_context_tokens,
            ),
            max_new_tokens=_positive_int("MODEL_MAX_NEW_TOKENS", 2048, maximum=8192),
            min_new_tokens=_positive_int("MODEL_MIN_NEW_TOKENS", 16, maximum=128),
            cpu_threads=_positive_int("LLM_STUDIO_CPU_THREADS", 3, maximum=16),
            request_timeout_seconds=_positive_int(
                "LLM_STUDIO_REQUEST_TIMEOUT_SECONDS", 900, maximum=3600
            ),
            max_concurrent_requests=_positive_int(
                "LLM_STUDIO_MAX_CONCURRENT_REQUESTS", 1, maximum=4
            ),
            queue_timeout_seconds=_positive_int(
                "LLM_STUDIO_QUEUE_TIMEOUT_SECONDS", 900, maximum=3600
            ),
            request_trace_logging=_boolean("LLM_STUDIO_REQUEST_TRACE_LOGGING", True),
            request_trace_log_path=os.getenv(
                "LLM_STUDIO_REQUEST_TRACE_LOG_PATH", "/data/logs/requests.jsonl"
            ),
            request_trace_max_content_chars=_positive_int(
                "LLM_STUDIO_REQUEST_TRACE_MAX_CONTENT_CHARS", 32768, maximum=1048576
            ),
        )


settings = Settings.from_environment()
