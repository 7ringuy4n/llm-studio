from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from .settings import settings


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
    return "authenticated"
