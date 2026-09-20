from __future__ import annotations

import hashlib
import hmac
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Header, HTTPException, status

from .settings import settings


class SlidingWindowRateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self._limit = requests_per_minute
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, identity: str) -> None:
        now = time.monotonic()
        threshold = now - 60.0
        with self._lock:
            events = self._events[identity]
            while events and events[0] < threshold:
                events.popleft()
            if len(events) >= self._limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": "60"},
                )
            events.append(now)


rate_limiter = SlidingWindowRateLimiter(settings.rate_limit_per_minute)


def require_api_key(authorization: str | None = Header(default=None)) -> str:
    scheme, separator, supplied_key = (authorization or "").partition(" ")
    valid = (
        separator == " "
        and scheme.lower() == "bearer"
        and hmac.compare_digest(supplied_key, settings.api_key)
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    identity = hashlib.sha256(supplied_key.encode("utf-8")).hexdigest()[:16]
    rate_limiter.check(identity)
    return identity

