from __future__ import annotations

import threading
from dataclasses import dataclass

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from .schemas import ChatCompletionRequest
from .settings import settings


@dataclass(frozen=True)
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


class ModelRuntime:
    def __init__(self) -> None:
        self._tokenizer = None
        self._model = None
        self._load_lock = threading.Lock()
        torch.set_num_threads(settings.cpu_threads)
        torch.set_num_interop_threads(1)

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self.loaded:
            return
        with self._load_lock:
            if self.loaded:
                return
            self._tokenizer = AutoTokenizer.from_pretrained(
                settings.model_id,
                revision=settings.model_revision,
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                settings.model_id,
                revision=settings.model_revision,
                torch_dtype=torch.float32,
                low_cpu_mem_usage=True,
            )
            self._model.eval()

    def generate(self, request: ChatCompletionRequest) -> GenerationResult:
        self.load()
        tokenizer = self._tokenizer
        model = self._model
        assert tokenizer is not None and model is not None

        messages = [message.model_dump() for message in request.messages]
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=settings.max_input_tokens,
        )
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        requested_tokens = request.max_tokens or min(256, settings.max_new_tokens)
        max_new_tokens = min(requested_tokens, settings.max_new_tokens)

        generation_kwargs = {
            "max_new_tokens": max_new_tokens,
            "pad_token_id": tokenizer.eos_token_id,
            "eos_token_id": tokenizer.eos_token_id,
        }
        if request.temperature == 0:
            generation_kwargs["do_sample"] = False
        else:
            generation_kwargs.update(
                do_sample=True,
                temperature=request.temperature,
                top_p=request.top_p,
            )
        if request.seed is not None:
            torch.manual_seed(request.seed)

        with torch.inference_mode():
            output = model.generate(**inputs, **generation_kwargs)

        generated_ids = output[0, prompt_tokens:]
        text = tokenizer.decode(generated_ids, skip_special_tokens=True)
        stop_sequences = [request.stop] if isinstance(request.stop, str) else request.stop or []
        for stop_sequence in stop_sequences:
            index = text.find(stop_sequence)
            if index >= 0:
                text = text[:index]
        completion_tokens = len(tokenizer.encode(text, add_special_tokens=False))
        return GenerationResult(text.strip(), prompt_tokens, completion_tokens)


runtime = ModelRuntime()

