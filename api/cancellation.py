"""Cooperative generation cancellation for llm-studio.

Clients (DeepSeek Harness Stop, aborted fetch, curl Ctrl-C) usually close the
HTTP connection. The API watches disconnect and flips a per-request cancel
token. Transformers StoppingCriteria / llama.cpp logits callbacks then stop
token loops so the VPS does not keep burning CPU after Stop.

An explicit ``POST /v1/generation/cancel`` covers clients that keep the socket
open while still wanting to abort by correlation / request id.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


class GenerationCancelled(Exception):
    """Raised when a generation is aborted by client disconnect or cancel API."""


@dataclass
class CancelToken:
    """Thread-safe cancel flag shared with worker-thread generation."""

    _event: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self._event.set()

    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise GenerationCancelled("generation cancelled by client")


class CancelRegistry:
    """Map client-visible ids → active cancel tokens."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, CancelToken] = {}

    def register(self, token: CancelToken, *keys: str | None) -> list[str]:
        registered: list[str] = []
        with self._lock:
            for key in keys:
                if not key:
                    continue
                cleaned = key.strip()
                if not cleaned:
                    continue
                self._tokens[cleaned] = token
                registered.append(cleaned)
        return registered

    def unregister(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._tokens.pop(key, None)

    def cancel(self, key: str) -> bool:
        cleaned = (key or "").strip()
        if not cleaned:
            return False
        with self._lock:
            token = self._tokens.get(cleaned)
        if token is None:
            return False
        token.cancel()
        return True

    def active_count(self) -> int:
        with self._lock:
            return len(self._tokens)


cancel_registry = CancelRegistry()
