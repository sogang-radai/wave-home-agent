from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ReportTurnState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: int
    domain: str
    period: str
    period_start: str
    metrics: dict[str, Any]
    raw: Optional[dict[str, Any]]
    rounds: int
    content: dict[str, Any]
