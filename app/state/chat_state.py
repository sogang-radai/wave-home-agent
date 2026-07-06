from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ChatTurnState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: int
    chat_history_id: int
    now: Optional[str]
    retrieved: list[dict[str, Any]]
    model: Optional[str]
    rounds: int
