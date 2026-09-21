#!/usr/bin/env python3
from __future__ import annotations

import sys
import types
from unittest.mock import patch

from api.model_catalog import BY_ID
from api.model_runtime import ALLOWED_BY_ID, ModelRuntime
from api.schemas import ChatCompletionRequest


class FakeCache:
    def __init__(self, capacity_bytes: int) -> None:
        self.capacity_bytes = capacity_bytes


class FakeLogitsProcessorList(list):
    def __call__(self, input_ids, scores):
        for processor in self:
            scores = processor(input_ids, scores)
        return scores


class FakeLlama:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.cache: FakeCache | None = None

    def set_cache(self, cache: FakeCache) -> None:
        self.cache = cache

    def create_chat_completion(self, **kwargs: object) -> dict[str, object]:
        messages = kwargs["messages"]
        assert isinstance(messages, list)
        assert str(messages[-1]["content"]).endswith("/no_think")
        processor = kwargs["logits_processor"]
        processor([], [0.0])
        return {
            "choices": [{"message": {"role": "assistant", "content": "<think>private</think>cache ready"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 4,
                "prompt_tokens_details": {"cached_tokens": 7},
            },
        }


def main() -> None:
    fake_module = types.ModuleType("llama_cpp")
    fake_module.Llama = FakeLlama
    fake_module.LlamaRAMCache = FakeCache
    fake_module.LogitsProcessorList = FakeLogitsProcessorList
    spec = BY_ID["Qwen/Qwen3-8B"]
    with (
        patch.dict(sys.modules, {"llama_cpp": fake_module}),
        patch.dict(ALLOWED_BY_ID, {spec.id: spec}),
        patch("api.model_runtime.hf_hub_download", return_value="/tmp/model.gguf"),
    ):
        runtime = ModelRuntime()
        runtime.load(spec.id)
        assert runtime.loaded_model_id == spec.id
        assert isinstance(runtime._model, FakeLlama)
        assert runtime._model.cache is not None
        result = runtime.generate(
            ChatCompletionRequest(
                model=spec.id,
                messages=[{"role": "user", "content": "test cache"}],
                reasoning_effort="off",
                max_tokens=8,
            )
        )
        assert result.text == "cache ready"
        assert result.reasoning is None
        assert result.prompt_tokens == 12
        assert result.cached_prompt_tokens == 7
        assert result.first_token_latency_ms is not None
        assert result.last_token_latency_ms is not None
        assert result.token_timing_source == "llama_cpp_logits_callback"
        runtime.unload()
        assert not runtime.loaded
    print("GGUF runtime, prompt cache, and unload regression passed")


if __name__ == "__main__":
    main()
