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


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw not in {"true", "false"}:
        raise RuntimeError(f"{name} must be true or false")
    return raw == "true"


@dataclass(frozen=True)
class Settings:
    api_key: str
    model_id: str
    model_revision: str
    model_load_on_start: bool
    max_input_tokens: int
    max_new_tokens: int
    cpu_threads: int
    request_timeout_seconds: int
    max_concurrent_requests: int
    rate_limit_per_minute: int

    @classmethod
    def from_environment(cls) -> "Settings":
        api_key = os.getenv("LLM_STUDIO_API_KEY", "")
        if len(api_key) < 32:
            raise RuntimeError("LLM_STUDIO_API_KEY must contain at least 32 characters")

        return cls(
            api_key=api_key,
            model_id=os.getenv("MODEL_ID", "Qwen/Qwen3.5-0.8B"),
            model_revision=os.getenv("MODEL_REVISION", "main"),
            model_load_on_start=_boolean("MODEL_LOAD_ON_START", False),
            max_input_tokens=_positive_int("MODEL_MAX_INPUT_TOKENS", 2048, maximum=8192),
            max_new_tokens=_positive_int("MODEL_MAX_NEW_TOKENS", 512, maximum=2048),
            cpu_threads=_positive_int("LLM_STUDIO_CPU_THREADS", 3, maximum=16),
            request_timeout_seconds=_positive_int(
                "LLM_STUDIO_REQUEST_TIMEOUT_SECONDS", 180, maximum=900
            ),
            max_concurrent_requests=_positive_int(
                "LLM_STUDIO_MAX_CONCURRENT_REQUESTS", 1, maximum=4
            ),
            rate_limit_per_minute=_positive_int(
                "LLM_STUDIO_RATE_LIMIT_PER_MINUTE", 30, maximum=600
            ),
        )


settings = Settings.from_environment()

