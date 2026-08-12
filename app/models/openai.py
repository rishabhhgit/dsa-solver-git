from __future__ import annotations

import time
import uuid
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field


class ImageUrl(BaseModel):
    url: str  # data:image/png;base64,... or a plain http(s) URL


class TextContentPart(BaseModel):
    type: Literal["text"]
    text: str


class ImageContentPart(BaseModel):
    type: Literal["image_url"]
    image_url: ImageUrl


ContentPart = Union[TextContentPart, ImageContentPart]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: Union[str, list[ContentPart]]


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex}")
    object: Literal["chat.completion"] = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)


class OpenAIErrorBody(BaseModel):
    message: str
    type: str
    param: Optional[str] = None
    code: Optional[str] = None


class OpenAIErrorResponse(BaseModel):
    error: OpenAIErrorBody


def make_error(message: str, error_type: str, code: str | None = None, param: str | None = None) -> dict:
    return OpenAIErrorResponse(error=OpenAIErrorBody(message=message, type=error_type, code=code, param=param)).model_dump()
