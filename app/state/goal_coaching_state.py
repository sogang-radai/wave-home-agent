from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class GoalCoachingState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: int
    goal_id: int
    goal_title: str
    category: str
    period_start: str
    rounds: int
    devices: list[dict[str, Any]]
    action_names_by_class: dict[str, set]
    # gather 가 결정적으로(tool loop 를 거치지 않고) 조회한 30일치 원본 행 — analyze 가 tool
    # 호출 결과 JSON 문자열을 다시 파싱할 필요 없이 바로 소비하게 하기 위함
    # (app/graph/insight_graph.py 의 devices/action_names_by_class 와 동일한 패턴).
    action_logs: list[dict[str, Any]]
    schedule_tasks: list[dict[str, Any]]
    stats: dict[str, Any]  # 결정적 "analyze" 노드가 채움
    content: Any  # GoalCoachingContent, generate 노드가 채움
