from __future__ import annotations

import base64
import ctypes
import gc
import io
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass

import torch
from huggingface_hub import hf_hub_download
from PIL import Image
from transformers import (
    AutoModelForCausalLM,
    AutoModelForMultimodalLM,
    AutoProcessor,
    AutoTokenizer,
    StoppingCriteria,
    StoppingCriteriaList,
)

from .model_catalog import ModelSpec, allowed_models
from .cancellation import CancelToken, GenerationCancelled
from .schemas import (
    ChatCompletionRequest,
    ImageURLContentPart,
    TextContentPart,
)
from .settings import settings
from .tracing import system_trace_context, trace_event

ALLOWED_MODELS = allowed_models(settings.model_allowed_models)
ALLOWED_BY_ID = {model.id: model for model in ALLOWED_MODELS}

TOOL_CALL_PATTERN = re.compile(
    r"<tool_call>\s*<function=([^>\n]+)>\s*(.*?)\s*</function>\s*</tool_call>",
    re.DOTALL,
)
TOOL_PARAMETER_PATTERN = re.compile(
    r"<parameter=([^>\n]+)>\s*(.*?)\s*</parameter>",
    re.DOTALL,
)


@dataclass(frozen=True)
class GeneratedToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class GenerationResult:
    text: str | None
    reasoning: str | None
    tool_calls: tuple[GeneratedToolCall, ...]
    prompt_tokens: int
    completion_tokens: int
    cached_prompt_tokens: int = 0
    first_token_latency_ms: float | None = None
    last_token_latency_ms: float | None = None
    token_timing_source: str = "backend_callback"


class _TokenTimingCriteria(StoppingCriteria):
    """Record token availability without changing generation stopping behavior."""

    def __init__(self, started: float) -> None:
        self.started = started
        self.first_token_latency_ms: float | None = None
        self.last_token_latency_ms: float | None = None

    def __call__(self, input_ids, scores, **kwargs) -> bool:
        elapsed = round((time.monotonic() - self.started) * 1000, 1)
        if self.first_token_latency_ms is None:
            self.first_token_latency_ms = elapsed
        self.last_token_latency_ms = elapsed
        return False


class _CancelStoppingCriteria(StoppingCriteria):
    """Stop Hugging Face generate() when the client cancel token is set."""

    def __init__(self, cancel_token: CancelToken | None) -> None:
        self.cancel_token = cancel_token

    def __call__(self, input_ids, scores, **kwargs) -> bool:
        return bool(self.cancel_token and self.cancel_token.cancelled())


class _GGUFTokenTimingProcessor:
    """Record llama.cpp sampling callbacks while leaving logits unchanged."""

    def __init__(self, started: float) -> None:
        self.started = started
        self.first_token_latency_ms: float | None = None
        self.last_token_latency_ms: float | None = None

    def __call__(self, input_ids, scores):
        elapsed = round((time.monotonic() - self.started) * 1000, 1)
        if self.first_token_latency_ms is None:
            self.first_token_latency_ms = elapsed
        self.last_token_latency_ms = elapsed
        return scores


class _GGUFCancelLogitsProcessor:
    """Abort llama.cpp sampling when the client cancel token is set."""

    def __init__(self, cancel_token: CancelToken | None) -> None:
        self.cancel_token = cancel_token

    def __call__(self, input_ids, scores):
        if self.cancel_token and self.cancel_token.cancelled():
            raise GenerationCancelled("generation cancelled by client")
        return scores

def _image_from_data_url(data_url: str) -> Image.Image:
    encoded = data_url.split(",", 1)[1]
    image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True)))
    image.load()
    return image.convert("RGB")


def _argument_value(value: str) -> object:
    value = value.strip()
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _parse_tool_calls(text: str) -> tuple[str | None, tuple[GeneratedToolCall, ...]]:
    calls: list[GeneratedToolCall] = []
    for match in TOOL_CALL_PATTERN.finditer(text):
        name = match.group(1).strip()
        arguments: dict[str, object] = {}
        for parameter in TOOL_PARAMETER_PATTERN.finditer(match.group(2)):
            arguments[parameter.group(1).strip()] = _argument_value(parameter.group(2))
        calls.append(
            GeneratedToolCall(
                id=f"call_{uuid.uuid4().hex}",
                name=name,
                arguments=json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
            )
        )
    if not calls:
        clean = text.strip()
        return (clean or None), ()
    clean = TOOL_CALL_PATTERN.sub("", text).strip()
    return (clean or None), tuple(calls)


def _split_reasoning(text: str, enabled: bool) -> tuple[str | None, str]:
    if not enabled or "</think>" not in text:
        return None, text
    reasoning, answer = text.split("</think>", 1)
    reasoning = reasoning.removeprefix("<think>").strip()
    return reasoning or None, answer.strip()


def _history_arguments(raw: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"input": raw}
    return value if isinstance(value, dict) else {"input": value}


class ModelRuntime:
    def __init__(self) -> None:
        self._processor = None
        self._tokenizer = None
        self._model = None
        self._loaded_model_id: str | None = None
        self._loaded_at: float | None = None
        self._idle_timer: threading.Timer | None = None
        self._last_used = 0.0
        self._load_lock = threading.Lock()
        torch.set_num_threads(settings.cpu_threads)
        try:
            torch.set_num_interop_threads(1)
        except RuntimeError:
            # PyTorch exposes this as process-global state and rejects a second
            # assignment after parallel work has started.
            pass

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def loaded_model_id(self) -> str | None:
        return self._loaded_model_id

    def _cancel_idle_locked(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def cancel_idle(self) -> None:
        with self._load_lock:
            self._cancel_idle_locked()

    def _unload_locked(self, reason: str = "manual") -> None:
        model_id = self._loaded_model_id
        loaded_at = self._loaded_at
        self._cancel_idle_locked()
        self._model = None
        self._processor = None
        self._tokenizer = None
        self._loaded_model_id = None
        self._loaded_at = None
        gc.collect()
        # PyTorch CPU tensors are freed above, but glibc may retain their
        # arenas in the process RSS. Return unused pages to the OS so an idle
        # model really releases host RAM instead of only becoming unreachable.
        try:
            libc = ctypes.CDLL(None)
            malloc_trim = libc.malloc_trim
            malloc_trim.argtypes = [ctypes.c_size_t]
            malloc_trim.restype = ctypes.c_int
            malloc_trim(0)
        except (AttributeError, OSError):
            # malloc_trim is a glibc extension; garbage collection is still
            # correct on platforms that do not expose it.
            pass
        if model_id is not None and loaded_at is not None:
            trace_event(
                "model_unloaded",
                system_trace_context("unload"),
                model_id=model_id,
                load_ms=None,
                resident_seconds=round(time.monotonic() - loaded_at, 3),
                reason=reason,
            )

    def unload(self, reason: str = "manual") -> None:
        with self._load_lock:
            self._unload_locked(reason=reason)

    def _unload_if_idle(self, last_used: float) -> None:
        with self._load_lock:
            if self._last_used == last_used:
                self._unload_locked(reason="idle")

    def mark_idle(self) -> None:
        with self._load_lock:
            self._cancel_idle_locked()
            self._last_used = time.monotonic()
            if settings.model_idle_unload_seconds == 0 or not self.loaded:
                return
            self._idle_timer = threading.Timer(
                settings.model_idle_unload_seconds,
                self._unload_if_idle,
                args=(self._last_used,),
            )
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def load(self, model_id: str | None = None, reason: str = "request") -> ModelSpec:
        selected_id = model_id or settings.model_id
        try:
            spec = ALLOWED_BY_ID[selected_id]
        except KeyError as exc:
            raise RuntimeError(f"model is not enabled: {selected_id}") from exc
        with self._load_lock:
            self._cancel_idle_locked()
            if self.loaded and self._loaded_model_id == spec.id:
                return spec
            if self.loaded:
                self._unload_locked(reason="switch")
            load_started = time.monotonic()
            common = {"revision": spec.revision}
            if spec.backend == "gguf":
                if not spec.gguf_filename:
                    raise RuntimeError(f"GGUF filename is missing for {spec.id}")
                from llama_cpp import Llama, LlamaRAMCache

                model_path = hf_hub_download(
                    repo_id=spec.download_repo_id,
                    filename=spec.gguf_filename,
                    revision=spec.revision,
                    local_files_only=True,
                )
                n_batch = settings.model_gguf_n_batch
                n_ubatch = min(settings.model_gguf_n_ubatch, n_batch)
                self._model = Llama(
                    model_path=model_path,
                    n_ctx=min(spec.context_tokens, settings.model_gguf_context_tokens),
                    n_threads=settings.cpu_threads,
                    n_threads_batch=settings.cpu_threads,
                    n_batch=n_batch,
                    n_ubatch=n_ubatch,
                    n_gpu_layers=0,
                    use_mmap=settings.model_gguf_use_mmap,
                    use_mlock=settings.model_gguf_use_mlock,
                    flash_attn=False,
                    verbose=False,
                )
                if settings.model_kv_cache_bytes:
                    owner = self._model

                    class TrackingLlamaRAMCache(LlamaRAMCache):
                        def __init__(self, capacity_bytes: int) -> None:
                            super().__init__(capacity_bytes=capacity_bytes)
                            self.last_cached_tokens = 0

                        def __getitem__(self, key):
                            self.last_cached_tokens = 0
                            value = super().__getitem__(key)
                            cache_prefix = Llama.longest_token_prefix(
                                value.input_ids.tolist(), list(key)
                            )
                            current_ids = getattr(owner, "_input_ids", [])
                            current_values = (
                                current_ids.tolist()
                                if hasattr(current_ids, "tolist")
                                else list(current_ids)
                            )
                            current_prefix = Llama.longest_token_prefix(
                                current_values, list(key)
                            )
                            self.last_cached_tokens = max(cache_prefix, current_prefix)
                            return value

                    self._model.set_cache(
                        TrackingLlamaRAMCache(
                            capacity_bytes=settings.model_kv_cache_bytes
                        )
                    )
                self._processor = "gguf"
            else:
                dtype: object = (
                    "auto" if spec.dtype == "auto" else getattr(torch, spec.dtype)
                )
                model_common = {
                    **common,
                    "dtype": dtype,
                    "low_cpu_mem_usage": True,
                }
                if spec.backend == "multimodal":
                    self._processor = AutoProcessor.from_pretrained(spec.id, **common)
                    self._tokenizer = self._processor.tokenizer
                    self._model = AutoModelForMultimodalLM.from_pretrained(
                        spec.id, **model_common
                    )
                else:
                    self._processor = AutoTokenizer.from_pretrained(spec.id, **common)
                    self._tokenizer = self._processor
                    self._model = AutoModelForCausalLM.from_pretrained(
                        spec.id, **model_common
                    )
            if spec.backend != "gguf":
                self._model.eval()
            self._loaded_model_id = spec.id
            self._loaded_at = time.monotonic()
            trace_event(
                "model_loaded",
                system_trace_context("load"),
                model_id=spec.id,
                load_ms=round((self._loaded_at - load_started) * 1000, 1),
                resident_seconds=0.0,
                reason=reason,
                backend=spec.backend,
            )
            return spec

    @staticmethod
    def _processor_messages(request: ChatCompletionRequest) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        for message in request.messages:
            role = "system" if message.role == "developer" else message.role
            if isinstance(message.content, str) or message.content is None:
                content: str | list[dict[str, object]] = message.content or ""
            else:
                content = []
                for part in message.content:
                    if isinstance(part, TextContentPart):
                        content.append({"type": "text", "text": part.text})
                    elif isinstance(part, ImageURLContentPart):
                        content.append(
                            {
                                "type": "image",
                                "image": _image_from_data_url(part.image_url.url),
                            }
                        )
            rendered: dict[str, object] = {"role": role, "content": content}
            if message.tool_calls:
                rendered["tool_calls"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": _history_arguments(call.function.arguments),
                        },
                    }
                    for call in message.tool_calls
                ]
            messages.append(rendered)
        return messages

    def generate(
        self,
        request: ChatCompletionRequest,
        cancel_token: CancelToken | None = None,
    ) -> GenerationResult:
        self.cancel_idle()
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        spec = self.load(request.model)
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        tools = None
        if request.tools and request.tool_choice != "none":
            tools = [tool.model_dump(exclude_none=True) for tool in request.tools]
        requested_tokens = request.requested_max_tokens or min(256, settings.max_new_tokens)
        max_new_tokens = min(requested_tokens, settings.max_new_tokens, spec.max_new_tokens)
        max_prompt_tokens = min(
            settings.max_input_tokens,
            spec.context_tokens - max_new_tokens,
        )
        if spec.backend == "gguf":
            max_prompt_tokens = min(
                max_prompt_tokens,
                settings.model_gguf_context_tokens - max_new_tokens,
            )
        if max_prompt_tokens < 1:
            raise RuntimeError("configured context window cannot fit the requested completion")

        if spec.backend == "gguf":
            return self._generate_gguf(request, spec, tools, max_new_tokens, cancel_token)

        processor = self._processor
        tokenizer = self._tokenizer
        model = self._model
        assert processor is not None and tokenizer is not None and model is not None

        template_kwargs: dict[str, object] = {
            "tools": tools,
            "add_generation_prompt": True,
            "tokenize": True,
            "return_dict": True,
            "return_tensors": "pt",
            "enable_thinking": request.thinking_enabled and spec.reasoning,
        }
        if spec.backend == "multimodal":
            template_kwargs["processor_kwargs"] = {
                "truncation": True,
                "max_length": max_prompt_tokens,
            }
        else:
            if any(not isinstance(message.content, (str, type(None))) for message in request.messages):
                raise RuntimeError(f"model does not accept image input: {spec.id}")
            template_kwargs.update(truncation=True, max_length=max_prompt_tokens)
        inputs = processor.apply_chat_template(
            self._processor_messages(request), **template_kwargs
        )
        inputs = inputs.to(model.device)
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()

        generation_kwargs: dict[str, object] = {
            "max_new_tokens": max_new_tokens,
            # Tiny checkpoints can choose EOS after one plausible word. Keep a
            # small bounded floor so interactive answers are useful.
            "min_new_tokens": min(settings.min_new_tokens, max_new_tokens),
            "pad_token_id": tokenizer.eos_token_id,
            "eos_token_id": tokenizer.eos_token_id,
            "repetition_penalty": request.repetition_penalty,
            # Reuse attention keys/values *within this generate() call only*.
            # Cross-request prompt prefix reuse (OpenObserve cache_hit_percent)
            # requires GGUF LlamaRAMCache — HF multimodal/text backends always
            # report cached_prompt_tokens=0 across HTTP turns.
            "use_cache": True,
        }
        if request.temperature == 0:
            generation_kwargs["do_sample"] = False
        else:
            generation_kwargs.update(
                do_sample=True,
                temperature=request.temperature,
                top_p=request.top_p,
            )
            if request.top_k is not None:
                generation_kwargs["top_k"] = request.top_k
            if request.min_p is not None:
                generation_kwargs["min_p"] = request.min_p
        if request.seed is not None:
            torch.manual_seed(request.seed)

        generation_started = time.monotonic()
        token_timing = _TokenTimingCriteria(generation_started)
        generation_kwargs["stopping_criteria"] = StoppingCriteriaList(
            [token_timing, _CancelStoppingCriteria(cancel_token)]
        )
        with torch.inference_mode():
            output = model.generate(**inputs, **generation_kwargs)
        if cancel_token is not None and cancel_token.cancelled():
            raise GenerationCancelled("generation cancelled by client")
        completed_latency_ms = round((time.monotonic() - generation_started) * 1000, 1)

        generated_ids = output[0, prompt_tokens:]
        raw_text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        stop_sequences = [request.stop] if isinstance(request.stop, str) else request.stop or []
        for stop_sequence in stop_sequences:
            index = raw_text.find(stop_sequence)
            if index >= 0:
                raw_text = raw_text[:index]
        reasoning, answer = _split_reasoning(
            raw_text, request.thinking_enabled and spec.reasoning
        )
        text, tool_calls = _parse_tool_calls(answer)
        return GenerationResult(
            text=text,
            reasoning=reasoning,
            tool_calls=tool_calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=int(generated_ids.shape[-1]),
            first_token_latency_ms=token_timing.first_token_latency_ms,
            last_token_latency_ms=token_timing.last_token_latency_ms or completed_latency_ms,
        )

    def _generate_gguf(
        self,
        request: ChatCompletionRequest,
        spec: ModelSpec,
        tools: list[dict[str, object]] | None,
        max_new_tokens: int,
        cancel_token: CancelToken | None = None,
    ) -> GenerationResult:
        model = self._model
        assert model is not None
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()
        messages: list[dict[str, object]] = []
        for message in request.messages:
            if not isinstance(message.content, (str, type(None))):
                raise RuntimeError(f"model does not accept image input: {spec.id}")
            rendered: dict[str, object] = {
                "role": "system" if message.role == "developer" else message.role,
                "content": message.content or "",
            }
            if message.tool_calls:
                rendered["tool_calls"] = [call.model_dump(exclude_none=True) for call in message.tool_calls]
            if message.tool_call_id:
                rendered["tool_call_id"] = message.tool_call_id
            messages.append(rendered)

        if spec.reasoning and not request.thinking_enabled:
            for message in reversed(messages):
                if message["role"] == "user":
                    message["content"] = f"{message['content']}\n/no_think"
                    break

        kwargs: dict[str, object] = {
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "top_k": request.top_k or 40,
            "min_p": request.min_p or 0.0,
            "repeat_penalty": request.repetition_penalty,
        }
        if request.stop is not None:
            kwargs["stop"] = [request.stop] if isinstance(request.stop, str) else request.stop
        if request.seed is not None:
            kwargs["seed"] = request.seed
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = request.tool_choice or "auto"

        generation_started = time.monotonic()
        token_timing = _GGUFTokenTimingProcessor(generation_started)
        from llama_cpp import LogitsProcessorList

        processors: list[object] = [token_timing]
        if cancel_token is not None:
            processors.append(_GGUFCancelLogitsProcessor(cancel_token))
        kwargs["logits_processor"] = LogitsProcessorList(processors)
        cache = getattr(model, "cache", None)
        if cache is not None and hasattr(cache, "last_cached_tokens"):
            cache.last_cached_tokens = 0
        try:
            response = model.create_chat_completion(**kwargs)
        except GenerationCancelled:
            raise
        except Exception:
            if cancel_token is not None and cancel_token.cancelled():
                raise GenerationCancelled("generation cancelled by client") from None
            raise
        if cancel_token is not None and cancel_token.cancelled():
            raise GenerationCancelled("generation cancelled by client")
        choice = response["choices"][0]
        message = choice["message"]
        raw_text = message.get("content") or ""
        parsed_reasoning, answer = _split_reasoning(raw_text, True)
        reasoning = message.get("reasoning_content") or parsed_reasoning
        if not request.thinking_enabled:
            reasoning = None
        generated_calls: list[GeneratedToolCall] = []
        for call in message.get("tool_calls") or []:
            function = call["function"]
            arguments = function.get("arguments", "{}")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
            generated_calls.append(
                GeneratedToolCall(
                    id=call.get("id") or f"call_{uuid.uuid4().hex}",
                    name=function["name"],
                    arguments=arguments,
                )
            )
        if not generated_calls:
            answer, parsed_calls = _parse_tool_calls(answer)
            generated_calls = list(parsed_calls)
        usage = response.get("usage") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        cached_prompt_tokens = int(prompt_details.get("cached_tokens", 0))
        if not cached_prompt_tokens and cache is not None:
            cached_prompt_tokens = int(getattr(cache, "last_cached_tokens", 0))
        completed_latency_ms = round((time.monotonic() - generation_started) * 1000, 1)
        return GenerationResult(
            text=(answer.strip() or None) if isinstance(answer, str) else answer,
            reasoning=reasoning,
            tool_calls=tuple(generated_calls),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            cached_prompt_tokens=cached_prompt_tokens,
            first_token_latency_ms=token_timing.first_token_latency_ms,
            last_token_latency_ms=token_timing.last_token_latency_ms or completed_latency_ms,
            token_timing_source="llama_cpp_logits_callback",
        )

    def request_interrupt(self) -> None:
        """Best-effort native interrupt for backends that expose it (GGUF)."""
        model = self._model
        if model is None:
            return
        interrupt = getattr(model, "interrupt", None)
        if callable(interrupt):
            try:
                interrupt()
            except Exception:  # noqa: BLE001 - optional fast-path only
                logger = __import__("logging").getLogger("llm_studio_api")
                logger.debug("model.interrupt() failed", exc_info=True)


runtime = ModelRuntime()
