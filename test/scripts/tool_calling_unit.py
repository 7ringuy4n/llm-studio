#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import asyncio
import json

from api.app import _completion_payload, _sse
from api.model_runtime import (
    GeneratedToolCall,
    GenerationResult,
    _parse_tool_calls,
    _split_reasoning,
)
from api.schemas import ChatCompletionRequest


def captured_request() -> dict[str, object]:
    return {
        "model": "Qwen/Qwen3.5-0.8B",
        "messages": [
            {"role": "developer", "content": "Use the provided tools when needed."},
            {"role": "user", "content": "What time is it? Use bash."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_previous",
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "arguments": "{\"command\":\"date\"}",
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "content": "12:00:00",
                "tool_call_id": "call_previous",
            },
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
        "store": False,
        "max_completion_tokens": 512,
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": "Run a bash command.",
                    "parameters": {
                        "type": "object",
                        "properties": {"command": {"type": "string"}},
                        "required": ["command"],
                    },
                    "strict": False,
                },
            }
        ],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "reasoning_effort": "low",
    }


def main() -> None:
    request = ChatCompletionRequest.model_validate(captured_request())
    assert request.requested_max_tokens == 512
    assert request.messages[2].tool_calls
    assert request.messages[3].tool_call_id == "call_previous"

    raw = """I will check.\n<tool_call>\n<function=bash>\n<parameter=command>\nTZ='Asia/Ho_Chi_Minh' date '+%H:%M:%S'\n</parameter>\n</function>\n</tool_call>"""
    text, calls = _parse_tool_calls(raw)
    assert text == "I will check."
    assert len(calls) == 1
    assert calls[0].name == "bash"
    assert json.loads(calls[0].arguments) == {
        "command": "TZ='Asia/Ho_Chi_Minh' date '+%H:%M:%S'"
    }

    reasoning, answer = _split_reasoning(
        "I should answer briefly.</think>\n\nThe answer is 42.", enabled=True
    )
    assert reasoning == "I should answer briefly."
    assert answer == "The answer is 42."

    result = GenerationResult(
        text=None,
        reasoning="I should use the bash tool.",
        tool_calls=(GeneratedToolCall("call_test", "bash", '{"command":"date"}'),),
        prompt_tokens=10,
        completion_tokens=5,
    )
    payload = _completion_payload("chatcmpl-test", 1, request, result)
    choice = payload["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["reasoning_content"] == "I should use the bash tool."
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "bash"

    async def streamed() -> str:
        return "".join([chunk async for chunk in _sse(payload, include_usage=True)])

    body = asyncio.run(streamed())
    assert body.index('"reasoning_content"') < body.index('"tool_calls"')
    assert '"finish_reason": "tool_calls"' in body
    assert '"choices": [], "usage"' in body
    assert body.endswith("data: [DONE]\n\n")
    print("tool calling regression passed")


if __name__ == "__main__":
    main()
