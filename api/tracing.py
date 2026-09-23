from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Mapping

from .settings import settings

TRACEPARENT = re.compile(r"^[\da-f]{2}-([\da-f]{32})-([\da-f]{16})-[\da-f]{2}$")
EXTERNAL_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
trace_logger = logging.getLogger("llm_studio_request_trace")
trace_logger.setLevel(logging.INFO)
trace_logger.propagate = False
_trace_ready = False


@dataclass(frozen=True)
class TraceContext:
    request_id: str
    session_id: str
    correlation_id: str
    trace_id: str
    span_id: str
    execution_id: str
    source_ip: str
    peer_ip: str
    forwarded_for: tuple[str, ...]


def _header(headers: Mapping[str, str], name: str) -> str:
    # Starlette Headers is case-insensitive; plain dicts used in tests are not.
    if hasattr(headers, "get"):
        direct = headers.get(name)
        if direct:
            return direct
        lower = name.lower()
        for key, value in headers.items():
            if key.lower() == lower and value:
                return value
    return ""


def _external_id(headers: Mapping[str, str], name: str, prefix: str) -> str:
    candidate = _header(headers, name)
    if EXTERNAL_ID.fullmatch(candidate):
        return candidate
    return f"{prefix}_{uuid.uuid4().hex}"


def _session_id(headers: Mapping[str, str]) -> str:
    # Prefer the llm-studio / OpenRouter header, then pi-ai openai affinity headers.
    for name in (
        "x-session-id",
        "x-session-affinity",
        "session_id",
        "x-client-request-id",
    ):
        candidate = _header(headers, name)
        if EXTERNAL_ID.fullmatch(candidate):
            return candidate
    return f"session_{uuid.uuid4().hex}"


def _valid_ip(value: str) -> str | None:
    candidate = value.strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def system_trace_context(event_prefix: str = "lifecycle") -> TraceContext:
    """Identity for process-lifecycle events that are not tied to an HTTP request."""
    return TraceContext(
        request_id=f"req_{event_prefix}_{uuid.uuid4().hex}",
        session_id=f"session_{event_prefix}",
        correlation_id=f"corr_{event_prefix}",
        trace_id=uuid.uuid4().hex,
        span_id=uuid.uuid4().hex[:16],
        execution_id=f"exec_{uuid.uuid4().hex}",
        source_ip="local",
        peer_ip="local",
        forwarded_for=(),
    )


def new_trace_context(headers: Mapping[str, str], peer_ip: str | None = None) -> TraceContext:
    trace_id = uuid.uuid4().hex
    validated_peer = _valid_ip(peer_ip or "") or "unknown"
    forwarded_for = tuple(
        address
        for item in _header(headers, "x-forwarded-for").split(",")
        if (address := _valid_ip(item)) is not None
    )
    # Traefik is the only network path to the un-published API container and
    # appends the directly connected client to the right of X-Forwarded-For.
    # Selecting the rightmost valid entry avoids trusting a client-supplied
    # prefix while retaining the original client address behind Traefik.
    source_ip = forwarded_for[-1] if forwarded_for else validated_peer
    traceparent = _header(headers, "traceparent").lower()
    match = TRACEPARENT.fullmatch(traceparent)
    if match and match.group(1) != "0" * 32 and match.group(2) != "0" * 16:
        trace_id = match.group(1)
    return TraceContext(
        request_id=_external_id(headers, "x-request-id", "req"),
        session_id=_session_id(headers),
        correlation_id=_external_id(headers, "x-correlation-id", "corr"),
        trace_id=trace_id,
        span_id=uuid.uuid4().hex[:16],
        execution_id=f"exec_{uuid.uuid4().hex}",
        source_ip=source_ip,
        peer_ip=validated_peer,
        forwarded_for=forwarded_for,
    )


def response_headers(context: TraceContext) -> dict[str, str]:
    return {
        "X-Request-ID": context.request_id,
        "X-Session-ID": context.session_id,
        "X-Correlation-ID": context.correlation_id,
        "X-Trace-ID": context.trace_id,
        "X-Span-ID": context.span_id,
        "X-Execution-ID": context.execution_id,
        "traceparent": f"00-{context.trace_id}-{context.span_id}-01",
    }


def _prepare_logger() -> bool:
    global _trace_ready
    if _trace_ready:
        return True
    if not settings.request_trace_logging:
        return False
    try:
        path = Path(settings.request_trace_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=50 * 1024 * 1024, backupCount=10, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        trace_logger.addHandler(handler)
        _trace_ready = True
    except OSError:
        logging.getLogger("llm_studio_api").exception("Request trace log is unavailable")
        return False
    return True


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        if value.startswith("data:image/"):
            return {
                "redacted": "embedded_image",
                "characters": len(value),
                "sha256": hashlib.sha256(value.encode()).hexdigest(),
            }
        maximum = settings.request_trace_max_content_chars
        if len(value) > maximum:
            return value[:maximum] + f"...[truncated {len(value) - maximum} characters]"
    return value


def trace_event(event: str, context: TraceContext, **fields: Any) -> None:
    if not _prepare_logger():
        return
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        **asdict(context),
        **_safe_value(fields),
    }
    try:
        trace_logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
    except (OSError, TypeError, ValueError):
        logging.getLogger("llm_studio_api").exception("Failed to write request trace")
