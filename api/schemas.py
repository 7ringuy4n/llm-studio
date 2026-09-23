from __future__ import annotations

import base64
import binascii
import io
import re
from typing import Annotated, Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_IMAGE_BYTES = 3 * 1024 * 1024
MAX_IMAGE_DIMENSION = 2048
MAX_TEXT_CHARS = 16 * 1024 * 1024
MAX_COMBINED_TEXT_BYTES = 16 * 1024 * 1024
IMAGE_DATA_URL = re.compile(
    r"^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\r\n]+)$"
)
FUNCTION_NAME = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class TextContentPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text"]
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class ImageURL(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=4_200_000)
    detail: Literal["auto", "low", "high"] | None = None

    @field_validator("url")
    @classmethod
    def validate_embedded_image(cls, value: str) -> str:
        match = IMAGE_DATA_URL.fullmatch(value)
        if not match:
            raise ValueError(
                "image_url.url must be an embedded PNG, JPEG, or WebP data URL; "
                "remote URLs and local paths are disabled"
            )
        try:
            payload = base64.b64decode(match.group(2), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image data URL contains invalid base64") from exc
        if not payload or len(payload) > MAX_IMAGE_BYTES:
            raise ValueError(f"decoded image must contain 1-{MAX_IMAGE_BYTES} bytes")
        try:
            with Image.open(io.BytesIO(payload)) as image:
                image.verify()
            with Image.open(io.BytesIO(payload)) as image:
                width, height = image.size
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise ValueError("image data URL is not a valid supported image") from exc
        if width < 1 or height < 1 or width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
            raise ValueError(
                f"image dimensions must be between 1 and {MAX_IMAGE_DIMENSION} pixels"
            )
        return value


class ImageURLContentPart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["image_url"]
    image_url: ImageURL


ContentPart = Annotated[
    TextContentPart | ImageURLContentPart,
    Field(discriminator="type"),
]


class FunctionCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: str = Field(max_length=65_536)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not FUNCTION_NAME.fullmatch(value):
            raise ValueError("function name must contain only letters, digits, underscores, or dashes")
        return value


class AssistantToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=256)
    type: Literal["function"] = "function"
    function: FunctionCall


class FunctionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = Field(default=None, max_length=16_384)
    parameters: dict[str, object] = Field(default_factory=dict)
    strict: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not FUNCTION_NAME.fullmatch(value):
            raise ValueError("function name must contain only letters, digits, underscores, or dashes")
        return value


class ChatTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["function"] = "function"
    function: FunctionDefinition


class StreamOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_usage: bool = False


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["developer", "system", "user", "assistant", "tool"]
    content: str | list[ContentPart] | None = None
    tool_calls: list[AssistantToolCall] | None = Field(default=None, max_length=32)
    tool_call_id: str | None = Field(default=None, min_length=1, max_length=256)
    name: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_content(self) -> "ChatMessage":
        if self.role == "tool":
            if not self.tool_call_id:
                raise ValueError("tool messages require tool_call_id")
            if not isinstance(self.content, str) or not self.content:
                raise ValueError("tool messages require non-empty text content")
            if self.tool_calls:
                raise ValueError("tool messages cannot contain tool_calls")
            return self
        if self.tool_call_id is not None:
            raise ValueError("tool_call_id is only valid on tool messages")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("tool_calls are only valid on assistant messages")
        if self.content is None or self.content == "":
            if self.role == "assistant" and self.tool_calls:
                return self
            raise ValueError("message content must not be empty")
        if isinstance(self.content, str):
            if len(self.content) > MAX_TEXT_CHARS:
                raise ValueError(
                    f"text content must contain at most {MAX_TEXT_CHARS} characters"
                )
            return self
        if not self.content or len(self.content) > 8:
            raise ValueError("multimodal content must contain 1-8 parts")
        if any(isinstance(part, ImageURLContentPart) for part in self.content):
            if self.role != "user":
                raise ValueError("only user messages may contain images")
        return self


class ChatTemplateKwargs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enable_thinking: bool = False


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    messages: list[ChatMessage] = Field(min_length=1, max_length=64)
    max_tokens: int | None = Field(default=None, ge=1)
    max_completion_tokens: int | None = Field(default=None, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=0, le=100)
    min_p: float | None = Field(default=None, ge=0.0, le=1.0)
    repetition_penalty: float = Field(default=1.0, gt=0.0, le=2.0)
    stream: bool = False
    stream_options: StreamOptions | None = None
    store: bool | None = None
    stop: str | list[str] | None = None
    seed: int | None = None
    n: Literal[1] = 1
    user: str | None = Field(default=None, max_length=256)
    tools: list[ChatTool] | None = Field(default=None, max_length=128)
    tool_choice: Literal["none", "auto", "required"] | dict[str, object] | None = None
    parallel_tool_calls: bool | None = None
    reasoning_effort: Literal["off", "none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = None
    enable_thinking: bool = False
    chat_template_kwargs: ChatTemplateKwargs | None = None

    @property
    def requested_max_tokens(self) -> int | None:
        return self.max_completion_tokens or self.max_tokens

    @property
    def thinking_enabled(self) -> bool:
        return self.enable_thinking or bool(
            self.chat_template_kwargs and self.chat_template_kwargs.enable_thinking
        ) or self.reasoning_effort not in (None, "off", "none")

    @model_validator(mode="after")
    def validate_message_payload(self) -> "ChatCompletionRequest":
        if self.max_tokens is not None and self.max_completion_tokens is not None:
            raise ValueError("use max_tokens or max_completion_tokens, not both")
        text_bytes = 0
        image_count = 0
        for message in self.messages:
            if isinstance(message.content, str):
                text_bytes += len(message.content.encode("utf-8"))
            elif message.content:
                for part in message.content:
                    if isinstance(part, TextContentPart):
                        text_bytes += len(part.text.encode("utf-8"))
                    else:
                        image_count += 1
            for tool_call in message.tool_calls or []:
                text_bytes += len(tool_call.function.arguments.encode("utf-8"))
        if text_bytes > MAX_COMBINED_TEXT_BYTES:
            raise ValueError("combined text and tool content is too large")
        if image_count > 2:
            raise ValueError("a request may contain at most two images")
        if self.tool_choice not in (None, "none") and not self.tools:
            raise ValueError("tool_choice requires tools")
        return self

    @field_validator("stop")
    @classmethod
    def validate_stop(cls, value: str | list[str] | None) -> str | list[str] | None:
        if isinstance(value, str) and len(value) > 256:
            raise ValueError("stop string is too long")
        if isinstance(value, list):
            if len(value) > 4 or any(not item or len(item) > 256 for item in value):
                raise ValueError("stop must contain 1-4 non-empty strings of <= 256 characters")
        return value


class CancelGenerationRequest(BaseModel):
    """Abort an in-flight chat completion by client-visible id."""

    model_config = ConfigDict(extra="forbid")

    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
