from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class LlmModel(BaseModel):
    id: str
    object: Literal["model"] = "model"
    role: Literal["chat", "embedding"]
    provider: str
    dimension: Optional[int] = None


class LlmModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[LlmModel] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(..., min_length=1)
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stop: Optional[Union[str, list[str]]] = None
    seed: Optional[int] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stream: bool = False


class EmbeddingRequest(BaseModel):
    model: str
    input: Union[str, list[str]]
