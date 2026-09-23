#!/usr/bin/env python3
"""Cancellation registry + Stop/cancel API contract (no live model)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_TEST_API_KEY = "0123456789abcdef0123456789abcdef"
os.environ["LLM_STUDIO_API_KEY"] = _TEST_API_KEY

from fastapi.testclient import TestClient

from api.app import app
from api.cancellation import CancelToken, GenerationCancelled, cancel_registry
from api.model_runtime import _CancelStoppingCriteria


def test_registry_cancel() -> None:
    token = CancelToken()
    keys = cancel_registry.register(token, "corr-1", "req-1")
    assert keys == ["corr-1", "req-1"]
    assert cancel_registry.cancel("corr-1") is True
    assert token.cancelled() is True
    cancel_registry.unregister(*keys)
    assert cancel_registry.cancel("corr-1") is False


def test_stopping_criteria() -> None:
    token = CancelToken()
    criteria = _CancelStoppingCriteria(token)
    assert criteria(None, None) is False
    token.cancel()
    assert criteria(None, None) is True


def test_cancel_endpoint() -> None:
    token = CancelToken()
    cancel_registry.register(token, "corr-endpoint-lab")
    with TestClient(app) as client:
        response = client.post(
            "/v1/generation/cancel",
            headers={"Authorization": f"Bearer {_TEST_API_KEY}"},
            json={"correlation_id": "corr-endpoint-lab"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["cancelled"] is True
    assert token.cancelled() is True
    cancel_registry.unregister("corr-endpoint-lab")


def test_chat_returns_499_when_cancelled() -> None:
    def fake_generate(request, cancel_token=None):
        assert cancel_token is not None
        cancel_token.cancel()
        raise GenerationCancelled("generation cancelled by client")

    with patch("api.app.runtime.generate", side_effect=fake_generate):
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {_TEST_API_KEY}",
                    "X-Correlation-ID": "corr-499-lab",
                },
                json={
                    "model": "Qwen/Qwen3.5-0.8B",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 8,
                },
            )
    assert response.status_code == 499, response.text
    assert response.json()["error"]["type"] == "cancelled_error"


def main() -> None:
    print("running test case 1/4: cancel registry", flush=True)
    test_registry_cancel()
    print("running test case 2/4: stopping criteria", flush=True)
    test_stopping_criteria()
    print("running test case 3/4: cancel endpoint", flush=True)
    test_cancel_endpoint()
    print("running test case 4/4: chat 499 on cancel", flush=True)
    test_chat_returns_499_when_cancelled()
    print("cancellation contract PASS: 4/4", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
