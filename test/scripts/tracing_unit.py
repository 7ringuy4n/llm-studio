#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import json
import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

# Force test key (must override a live container's LLM_STUDIO_API_KEY).
_TEST_API_KEY = "0123456789abcdef0123456789abcdef"
os.environ["LLM_STUDIO_API_KEY"] = _TEST_API_KEY
trace_file = Path(tempfile.gettempdir()) / f"llm-studio-tracing-{os.getpid()}.jsonl"
os.environ["LLM_STUDIO_REQUEST_TRACE_LOG_PATH"] = str(trace_file)

from fastapi.testclient import TestClient

from api.app import app
from api.model_runtime import GenerationResult
from api.tracing import new_trace_context


def fake_generate(request) -> GenerationResult:
    time.sleep(0.03)
    content = request.messages[-1].content
    return GenerationResult(
        text=f"reply:{content}",
        reasoning=None,
        tool_calls=(),
        prompt_tokens=100,
        completion_tokens=20,
        cached_prompt_tokens=75,
        first_token_latency_ms=10.5,
        last_token_latency_ms=25.5,
    )


def assert_session_affinity_headers() -> None:
    affinity = "session-dsh-abc-123"
    cases = (
        ({"x-session-id": affinity}, affinity),
        ({"x-session-affinity": affinity}, affinity),
        ({"session_id": affinity}, affinity),
        ({"X-Session-Affinity": affinity}, affinity),
        (
            {"x-session-affinity": "session-affinity-fallback", "x-session-id": "session-preferred"},
            "session-preferred",
        ),
    )
    for headers, expected in cases:
        context = new_trace_context(headers, "127.0.0.1")
        assert context.session_id == expected, (headers, context.session_id)


def main() -> None:
    assert_session_affinity_headers()

    session_id = "session-concurrency-test"
    correlation_id = "corr-concurrency-test"
    trace_id = "a" * 32
    barrier = threading.Barrier(3)

    def send(client: TestClient, index: int):
        barrier.wait()
        return client.post(
                "/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {_TEST_API_KEY}",
                    "X-Session-ID": session_id,
                    "X-Correlation-ID": correlation_id,
                    "X-Forwarded-For": f"198.51.100.{index + 10}",
                    "traceparent": f"00-{trace_id}-{index + 1:016x}-01",
                },
                json={
                    "model": "Qwen/Qwen3.5-0.8B",
                    "messages": [{"role": "user", "content": f"request-{index}"}],
                    "max_tokens": 32,
                },
        )

    def send_affinity(client: TestClient):
        return client.post(
            "/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {_TEST_API_KEY}",
                "x-session-affinity": "session-affinity-roundtrip",
                "X-Forwarded-For": "198.51.100.50",
            },
            json={
                "model": "Qwen/Qwen3.5-0.8B",
                "messages": [{"role": "user", "content": "affinity"}],
                "max_tokens": 32,
            },
        )

    try:
        with patch("api.app.runtime.generate", side_effect=fake_generate):
            with TestClient(app) as client, ThreadPoolExecutor(max_workers=3) as executor:
                responses = list(executor.map(lambda index: send(client, index), range(3)))
                affinity_response = send_affinity(client)

        assert all(response.status_code == 200 for response in responses)
        assert {response.headers["x-session-id"] for response in responses} == {session_id}
        assert {response.headers["x-correlation-id"] for response in responses} == {correlation_id}
        assert {response.headers["x-trace-id"] for response in responses} == {trace_id}
        assert len({response.headers["x-request-id"] for response in responses}) == 3
        assert len({response.headers["x-span-id"] for response in responses}) == 3
        assert len({response.headers["x-execution-id"] for response in responses}) == 3
        for response in responses:
            assert response.headers["x-first-token-ms"] == "10.5"
            assert response.headers["x-last-token-ms"] == "25.5"
            assert response.headers["x-cache-hit-percent"] == "75.0"
            assert response.headers["x-input-tokens"] == "100"
            assert response.headers["x-output-tokens"] == "20"
            assert "first-token;dur=10.5" in response.headers["server-timing"]

        assert affinity_response.status_code == 200
        assert affinity_response.headers["x-session-id"] == "session-affinity-roundtrip"

        records = [json.loads(line) for line in trace_file.read_text().splitlines()]
        completed = [record for record in records if record["event"] == "model_response_completed"]
        assert len(completed) == 4
        assert {record["session_id"] for record in completed[:3]} == {session_id}
        assert completed[3]["session_id"] == "session-affinity-roundtrip"
        assert {record["correlation_id"] for record in completed[:3]} == {correlation_id}
        assert {record["trace_id"] for record in completed[:3]} == {trace_id}
        assert {record["source_ip"] for record in completed[:3]} == {
            "198.51.100.10", "198.51.100.11", "198.51.100.12"
        }
        assert all(record["input_tokens"] == 100 for record in completed)
        assert all(record["output_tokens"] == 20 for record in completed)
        assert all(record["cached_input_tokens"] == 75 for record in completed)
        assert all(record["cache_hit_percent"] == 75.0 for record in completed)
        assert all(record["response"]["choices"][0]["message"]["content"].startswith("reply:") for record in completed)
    finally:
        trace_file.unlink(missing_ok=True)
    print("concurrent request tracing, token timing, cache, IDs, IP, affinity, and response capture passed")


if __name__ == "__main__":
    main()
