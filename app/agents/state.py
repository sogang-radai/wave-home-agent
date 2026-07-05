from typing import Any, Literal, Optional, TypedDict


AgentTask = Literal[
    "chat",
    "weekly_sleep_report",
    "nightly_sleep_report",
    "weekly_posture_report",
    "daily_posture_report",
    "recommend_actions",
]


class AgentState(TypedDict, total=False):
    task: AgentTask
    account_id: str
    user_message: Optional[str]
    metadata: dict[str, Any]
    context: dict[str, Any]
    intent: str
    answer: str
    title: str
    summary: str
    highlights: list[str]
    recommendations: list[str]
    actions: list[dict[str, Any]]
    sources: list[str]
