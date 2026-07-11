from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class InsightGenerationState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: int
    surface: str
    date: str
    context: dict[str, Any]
    rounds: int
    generate_attempts: int
    items: list[dict[str, Any]]
    devices: list[dict[str, Any]]
    action_names_by_class: dict[str, set[str]]
