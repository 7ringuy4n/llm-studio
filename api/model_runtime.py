from __future__ import annotations

import base64
import io
import threading
from dataclasses import dataclass

import torch
from PIL import Image
from transformers import AutoModelForMultimodalLM, AutoProcessor

from .schemas import (
    ChatCompletionRequest,
    ImageURLContentPart,
    TextContentPart,
)
from .settings import settings


@dataclass(frozen=True)
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


def _image_from_data_url(data_url: str) -> Image.Image:
    encoded = data_url.split(",", 1)[1]
    image = Image.open(io.BytesIO(base64.b64decode(encoded, validate=True)))
    image.load()
    return image.convert("RGB")


class ModelRuntime:
    def __init__(self) -> None:
        self._processor = None
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
            self._processor = AutoProcessor.from_pretrained(
                settings.model_id,
                revision=settings.model_revision,
            )
            self._model = AutoModelForMultimodalLM.from_pretrained(
                settings.model_id,
                revision=settings.model_revision,
                dtype=torch.float32,
                low_cpu_mem_usage=True,
            )
            self._model.eval()

    @staticmethod
    def _processor_messages(request: ChatCompletionRequest) -> list[dict[str, object]]:
        messages: list[dict[str, object]] = []
        for message in request.messages:
            if isinstance(message.content, str):
                messages.append({"role": message.role, "content": message.content})
                continue
            content: list[dict[str, object]] = []
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
            messages.append({"role": message.role, "content": content})
        return messages

    def generate(self, request: ChatCompletionRequest) -> GenerationResult:
        self.load()
        processor = self._processor
        model = self._model
        assert processor is not None and model is not None

        inputs = processor.apply_chat_template(
            self._processor_messages(request),
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            processor_kwargs={
                "truncation": True,
                "max_length": settings.max_input_tokens,
            },
            enable_thinking=request.thinking_enabled,
        )
        inputs = inputs.to(model.device)
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        requested_tokens = request.max_tokens or min(256, settings.max_new_tokens)
        max_new_tokens = min(requested_tokens, settings.max_new_tokens)

        generation_kwargs: dict[str, object] = {
            "max_new_tokens": max_new_tokens,
            "pad_token_id": processor.tokenizer.eos_token_id,
            "eos_token_id": processor.tokenizer.eos_token_id,
            "repetition_penalty": request.repetition_penalty,
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

        with torch.inference_mode():
            output = model.generate(**inputs, **generation_kwargs)

        generated_ids = output[0, prompt_tokens:]
        text = processor.decode(generated_ids, skip_special_tokens=True)
        stop_sequences = [request.stop] if isinstance(request.stop, str) else request.stop or []
        for stop_sequence in stop_sequences:
            index = text.find(stop_sequence)
            if index >= 0:
                text = text[:index]
        completion_tokens = len(
            processor.tokenizer.encode(text, add_special_tokens=False)
        )
        return GenerationResult(text.strip(), prompt_tokens, completion_tokens)


runtime = ModelRuntime()
