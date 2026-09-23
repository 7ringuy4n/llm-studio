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
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("LLM_STUDIO_API_KEY", "0123456789abcdef0123456789abcdef")
trace_file = Path(tempfile.gettempdir()) / f"llm-studio-model-mgmt-{os.getpid()}.jsonl"
os.environ["LLM_STUDIO_REQUEST_TRACE_LOGGING"] = "true"
os.environ["LLM_STUDIO_REQUEST_TRACE_LOG_PATH"] = str(trace_file)

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
    trace_file.unlink(missing_ok=True)
    runtime = ModelRuntime()
    with (
        patch("api.model_runtime.AutoProcessor.from_pretrained", return_value=DummyProcessor()),
        patch("api.model_runtime.AutoModelForMultimodalLM.from_pretrained", return_value=DummyModel()),
    ):
        runtime.load("Qwen/Qwen3.5-0.8B", reason="startup")
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

    records = [json.loads(line) for line in trace_file.read_text().splitlines()]
    loaded = [record for record in records if record["event"] == "model_loaded"]
    unloaded = [record for record in records if record["event"] == "model_unloaded"]
    assert len(loaded) == 2
    assert loaded[0]["model_id"] == "Qwen/Qwen3.5-0.8B"
    assert loaded[0]["reason"] == "startup"
    assert isinstance(loaded[0]["load_ms"], (int, float))
    assert loaded[0]["resident_seconds"] == 0.0
    assert loaded[1]["model_id"] == "Qwen/Qwen3.5-2B"
    assert loaded[1]["reason"] == "request"
    assert len(unloaded) == 2
    assert unloaded[0]["model_id"] == "Qwen/Qwen3.5-0.8B"
    assert unloaded[0]["reason"] == "switch"
    assert unloaded[0]["resident_seconds"] >= 0
    assert unloaded[1]["model_id"] == "Qwen/Qwen3.5-2B"
    assert unloaded[1]["reason"] == "idle"
    assert unloaded[1]["resident_seconds"] >= 1.0
    trace_file.unlink(missing_ok=True)
    print("model switching, idle unload, and load/unload tracing regression passed")


if __name__ == "__main__":
    main()
