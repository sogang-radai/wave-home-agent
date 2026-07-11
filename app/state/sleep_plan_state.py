from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from app.schemas.sleep_plan import SleepPlanContent


class SleepPlanState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: int
    plan_date: str
    rounds: int
    content: "SleepPlanContent | None"
