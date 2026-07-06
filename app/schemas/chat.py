from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class RetrievedSnippet(BaseModel):
    collection: str
    refId: Optional[int] = None
    text: str


class ChatContext(BaseModel):
    now: Optional[str] = None
    retrieved: list[RetrievedSnippet] = Field(default_factory=list)


class ChatTurnRequest(BaseModel):
    chatHistoryId: int
    userId: int
    messages: list[ChatMessage] = Field(..., min_length=1)
    context: ChatContext = Field(default_factory=ChatContext)
    model: Optional[str] = None
    stream: bool = True


class ToolCallRecord(BaseModel):
    name: str
    args: dict[str, Any]
    ok: bool
    result: Optional[Any] = None


class ChatTurnResponse(BaseModel):
    content: str
    model: str
    toolCalls: list[ToolCallRecord] = Field(default_factory=list)
