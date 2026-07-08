"""weekly-plan-analysis-api.md 의 `/weekly-plan/v1/reports` 생성 그래프.

app/graph/report_turn_graph.py 와 동일한 gather->generate 패턴. 문서 명시대로 metrics 를
인라인으로 받지 않고, 에이전트가 db/query·rag/search 로 직접 조회한다.

WEEKLY_PLAN_TABLES/WEEKLY_PLAN_RAG_COLLECTIONS 는 문서에 명시되지 않은 추정치다
(db-schema.md 의 schedule_task/sleep_report/posture_report/weekly_plan_report 근거).
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from app.graph.tool_loop import build_tool_loop
from app.graph.tools import make_query_db_tool, make_rag_search_tool
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.weekly_plan_state import WeeklyPlanReportState


MAX_CONTEXT_ROUNDS = 2

WEEKLY_PLAN_TABLES: set[str] = {"schedule_task", "sleep_report", "posture_report", "weekly_plan_report"}
WEEKLY_PLAN_RAG_COLLECTIONS: set[str] = {"weekly_plan_report", "insight_weekly_plan", "sleep_report", "posture_report"}

_CONTEXT_SYSTEM_PROMPT = """당신은 WaveHome 주간 계획 배너 작성을 돕는 조사자입니다.
이번 주 일정(schedule_task), 수면/자세 리포트를 db/query·rag_search 로 조회하세요.
필요 없으면 tool을 호출하지 말고 "충분합니다"라고만 답하세요."""


class WeeklyPlanContent(BaseModel):
    headline: str | None = None
    reportText: str


def _seed_message(state: WeeklyPlanReportState) -> HumanMessage:
    return HumanMessage(content=f"이번 주 월요일: {state['period_start']}")


def _extract_tool_results(messages: list[Any]) -> list[Any]:
    extra = []
    for message in messages:
        if isinstance(message, ToolMessage):
            try:
                extra.append(json.loads(str(message.content)))
            except (TypeError, ValueError):
                extra.append(str(message.content))
    return extra


def _rule_based_content(state: WeeklyPlanReportState) -> WeeklyPlanContent:
    return WeeklyPlanContent(
        headline="이번 주도 화이팅!",
        reportText="이번 주 계획을 확인하고 꾸준히 실천해보세요.",
    )


async def gather(state: WeeklyPlanReportState) -> dict[str, Any]:
    tools = [
        make_query_db_tool(state["user_id"], allowed_tables=WEEKLY_PLAN_TABLES),
        make_rag_search_tool(allowed_collections=WEEKLY_PLAN_RAG_COLLECTIONS),
    ]
    loop = build_tool_loop(
        WeeklyPlanReportState,
        tools,
        max_rounds=MAX_CONTEXT_ROUNDS,
        system_prompt_fn=lambda _state: _CONTEXT_SYSTEM_PROMPT,
    )
    result = await loop.ainvoke({"messages": [_seed_message(state)], "rounds": 0})
    return {"messages": result["messages"]}


async def generate(state: WeeklyPlanReportState) -> dict[str, Any]:
    extra_context = _extract_tool_results(state.get("messages", []))
    prompt = load_prompt(
        "weekly_plan",
        "report",
        user_id=state["user_id"],
        period_start=state["period_start"],
        extra_context=json.dumps(extra_context, ensure_ascii=False),
    )
    content = await invoke_structured(WeeklyPlanContent, prompt, fallback=_rule_based_content(state))
    return {"headline": content.headline, "report_text": content.reportText}


def build():
    graph = StateGraph(WeeklyPlanReportState)
    graph.add_node("gather", gather)
    graph.add_node("generate", generate)
    graph.set_entry_point("gather")
    graph.add_edge("gather", "generate")
    graph.add_edge("generate", END)
    return graph.compile()