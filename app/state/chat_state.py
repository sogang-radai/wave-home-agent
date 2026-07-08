import operator
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
    domains: Optional[list[str]]
    # 2+ domain nodes can run in the same superstep (turn_graph.py's Send
    # fan-out) and each appends its own {domain, text} entry here in the same
    # step, so this needs a reducer (plain overwrite would raise
    # InvalidUpdateError on concurrent writes to the same channel).
    domain_answers: Annotated[list[dict[str, Any]], operator.add]
