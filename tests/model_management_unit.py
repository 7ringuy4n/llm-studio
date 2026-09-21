#!/usr/bin/env python3
from __future__ import annotations

import time
from unittest.mock import patch

from api.model_runtime import ModelRuntime
from api.settings import settings


class DummyTokenizer:
    eos_token_id = 1


class DummyProcessor:
    tokenizer = DummyTokenizer()


class DummyModel:
    def eval(self) -> None:
        return None


def main() -> None:
    runtime = ModelRuntime()
    with (
        patch("api.model_runtime.AutoProcessor.from_pretrained", return_value=DummyProcessor()),
        patch("api.model_runtime.AutoModelForMultimodalLM.from_pretrained", return_value=DummyModel()),
    ):
        runtime.load("Qwen/Qwen3.5-0.8B")
        assert runtime.loaded_model_id == "Qwen/Qwen3.5-0.8B"
        runtime.load("Qwen/Qwen3.5-2B")
        assert runtime.loaded_model_id == "Qwen/Qwen3.5-2B"

    original = settings.model_idle_unload_seconds
    object.__setattr__(settings, "model_idle_unload_seconds", 1)
    try:
        runtime.mark_idle()
        time.sleep(1.2)
        assert not runtime.loaded
        assert runtime.loaded_model_id is None
    finally:
        object.__setattr__(settings, "model_idle_unload_seconds", original)
    print("model switching and idle unload regression passed")


if __name__ == "__main__":
    main()
