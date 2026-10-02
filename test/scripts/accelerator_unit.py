#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("LLM_STUDIO_API_KEY", "0123456789abcdef0123456789abcdef")
os.environ["LLM_STUDIO_ACCELERATOR"] = "cpu"

from api.settings import Settings


def _settings_cases() -> None:
    cpu = Settings.from_environment()
    assert cpu.accelerator == "cpu"
    assert cpu.model_gguf_n_gpu_layers == -1

    with patch.dict(os.environ, {"LLM_STUDIO_ACCELERATOR": "cuda"}, clear=False):
        cuda = Settings.from_environment()
        assert cuda.accelerator == "cuda"

    with patch.dict(os.environ, {"LLM_STUDIO_ACCELERATOR": "auto"}, clear=False):
        try:
            Settings.from_environment()
            raise AssertionError("auto must be rejected by the API settings loader")
        except RuntimeError as exc:
            assert "cpu" in str(exc) and "cuda" in str(exc)


def _gguf_gpu_layers_cases() -> None:
    import importlib

    import api.model_runtime as runtime_mod

    importlib.reload(runtime_mod)
    from api.model_catalog import BY_ID
    from api.model_runtime import ALLOWED_BY_ID, ModelRuntime

    fake_module = types.ModuleType("llama_cpp")

    class FakeLlama:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def set_cache(self, cache: object) -> None:
            self.cache = cache

    class FakeCache:
        def __init__(self, capacity_bytes: int) -> None:
            self.capacity_bytes = capacity_bytes

    fake_module.Llama = FakeLlama
    fake_module.LlamaRAMCache = FakeCache
    fake_module.LogitsProcessorList = list
    spec = BY_ID["Qwen/Qwen3-8B"]

    with (
        patch.dict(sys.modules, {"llama_cpp": fake_module}),
        patch.dict(ALLOWED_BY_ID, {spec.id: spec}),
        patch("api.model_runtime.hf_hub_download", return_value="/tmp/model.gguf"),
        patch.object(runtime_mod.settings, "accelerator", "cpu"),
        patch.object(runtime_mod.settings, "model_gguf_n_gpu_layers", -1),
    ):
        runtime = ModelRuntime()
        runtime.load(spec.id)
        assert runtime._model.kwargs.get("n_gpu_layers") == 0
        runtime.unload()

    with (
        patch.dict(sys.modules, {"llama_cpp": fake_module}),
        patch.dict(ALLOWED_BY_ID, {spec.id: spec}),
        patch("api.model_runtime.hf_hub_download", return_value="/tmp/model.gguf"),
        patch.object(runtime_mod.settings, "accelerator", "cuda"),
        patch.object(runtime_mod.settings, "model_gguf_n_gpu_layers", -1),
    ):
        runtime = ModelRuntime()
        runtime.load(spec.id)
        assert runtime._model.kwargs.get("n_gpu_layers") == -1
        runtime.unload()


def main() -> None:
    _settings_cases()
    try:
        import torch  # noqa: F401
    except ImportError:
        print("Accelerator settings passed (GGUF runtime skipped: no torch)")
        return
    _gguf_gpu_layers_cases()
    print("Accelerator settings and GGUF n_gpu_layers regression passed")


if __name__ == "__main__":
    main()
