from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=32_768)


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    messages: list[ChatMessage] = Field(min_length=1, max_length=64)
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, gt=0.0, le=1.0)
    stream: bool = False
    stop: str | list[str] | None = None
    seed: int | None = None
    n: Literal[1] = 1
    user: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def validate_total_message_size(self) -> "ChatCompletionRequest":
        if sum(len(message.content.encode("utf-8")) for message in self.messages) > 60_000:
            raise ValueError("combined message content is too large")
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
