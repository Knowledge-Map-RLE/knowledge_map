"""Pydantic schemas for the OpenAI-compatible chat endpoint.

The request schema accepts the standard OpenAI ``chat/completions`` body plus any
extra keys (e.g. ``top_k``), which are forwarded to the upstream provider
unchanged.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., pattern="^(system|user|assistant|tool)$")
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""

    model_config = ConfigDict(extra="allow")

    model: str | None = Field(default=None)
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = Field(default=False)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
