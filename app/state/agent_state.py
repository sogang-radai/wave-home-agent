import operator
from typing import Annotated, Any, Literal, Optional, TypedDict


AgentTask = Literal[
    "chat",
    "weekly_sleep_report",
    "nightly_sleep_report",
    "weekly_posture_report",
    "daily_posture_report",
    "recommend_actions",
]


class AgentState(TypedDict, total=False):
    # Supervisor-level (interface.md Global State)
    user_id: str
    session_id: Optional[str]
    task: AgentTask
    request: dict[str, Any]
    intent: str
    required_context: list[str]
    tool_results: dict[str, Any]
    health_insights: dict[str, Any]
    report: dict[str, Any]
    action_plan: dict[str, Any]
    action_result: dict[str, Any]
    response: str

    # External-response-shaped fields. LangGraph only tracks keys declared
    # here, so every field any graph writes for the final REST response
    # (app/schemas/agent.py) must be declared, or the write is silently
    # dropped (see langgraph/pregel/algo.py::apply_writes).
    answer: str
    title: str
    summary: str
    highlights: list[str]
    recommendations: list[str]
    actions: list[dict[str, Any]]
    sources: list[str]

    # HealthAnalysisGraph fan-out-only keys. Each domain agent writes only its
    # own key, so the default LastValue channel is safe for parallel writes.
    sleep_insight: dict[str, Any]
    posture_insight: dict[str, Any]
    observation_insight: dict[str, Any]
    lifestyle_insight: dict[str, Any]

    # Multiple parallel branches may append here in the same step, so this
    # key needs a reducer to avoid LangGraph's InvalidUpdateError.
    errors: Annotated[list[str], operator.add]
