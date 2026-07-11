"""'오늘 밤 추천 수면 시간' agent job(app/services/sleep_analysis.py 의 PLAN_KIND) 그래프.

app/graph/weekly_plan_graph.py 와 동일한 gather->generate 패턴. C++ 백엔드가 이미
GET /api/v1/sleep/today/plan 에서 sleep_session 평균 수면 시간 + 다음날 schedule_task
최이른 시작 시각으로 결정론적 추천값을 sleep_plan 테이블에 캐싱해두고 있고, 이 그래프는
그 신호를 agent 가 독립적으로 db/query·rag_search 로 다시 조회해 더 나은 자연어 근거와
다듬어진 취침/기상 추천을 만든다(캐시 row 를 이 결과로 보강하는 배선은 이 작업 범위 밖).

SLEEP_PLAN_TABLES 는 user_sleep_config 를 포함하지 않는다 — app/tools/db_query.py 의
TABLE_SPECS 에 아직 등록되어 있지 않아, 이 그래프 범위에서 새 테이블 스펙을 추가하는
부수효과를 내지 않기 위해 뺐다.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph

from app.graph.tool_loop import build_tool_loop
from app.graph.tools import make_query_db_tool, make_rag_search_tool
from app.schemas.sleep_plan import SleepPlanContent
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.sleep_plan_state import SleepPlanState


MAX_CONTEXT_ROUNDS = 2

SLEEP_PLAN_TABLES: set[str] = {"sleep_session", "sleep_stat", "sleep_report", "schedule_task"}
SLEEP_PLAN_RAG_COLLECTIONS: set[str] = {"sleep_report"}

_CONTEXT_SYSTEM_PROMPT = """당신은 WaveHome 오늘 밤 추천 수면 시간을 조사하는 조사자입니다.
최근 7일 정도의 수면 기록(sleep_session)과 다음날 일정(schedule_task) 을 db/query·rag_search 로
조회하세요. 필요 없으면 tool을 호출하지 말고 "충분합니다"라고만 답하세요."""


def _seed_message(state: SleepPlanState) -> HumanMessage:
    return HumanMessage(
        content=f"사용자 {state['user_id']} 의 {state['plan_date']} 밤 수면 계획을 세우기 위해 "
        "최근 수면 기록과 다음날 일정을 조회하세요."
    )


def _extract_tool_results(messages: list[Any]) -> list[Any]:
    extra = []
    for message in messages:
        if isinstance(message, ToolMessage):
            try:
                extra.append(json.loads(str(message.content)))
            except (TypeError, ValueError):
                extra.append(str(message.content))
    return extra


def _rule_based_content(state: SleepPlanState) -> SleepPlanContent:
    return SleepPlanContent(
        bedtimeMinute=23 * 60 + 30,
        wakeMinute=7 * 60,
        targetDurationMinutes=450,
        rationale="충분한 데이터가 없어 기본 권장 수면 시간을 제안했어요.",
    )


async def gather(state: SleepPlanState) -> dict[str, Any]:
    tools = [
        make_query_db_tool(state["user_id"], allowed_tables=SLEEP_PLAN_TABLES),
        make_rag_search_tool(allowed_collections=SLEEP_PLAN_RAG_COLLECTIONS),
    ]
    loop = build_tool_loop(
        SleepPlanState,
        tools,
        max_rounds=MAX_CONTEXT_ROUNDS,
        system_prompt_fn=lambda _state: _CONTEXT_SYSTEM_PROMPT,
    )
    result = await loop.ainvoke({"messages": [_seed_message(state)], "rounds": 0})
    return {"messages": result["messages"]}


async def generate(state: SleepPlanState) -> dict[str, Any]:
    extra_context = _extract_tool_results(state.get("messages", []))
    prompt = load_prompt(
        "sleep_plan",
        "generate",
        user_id=state["user_id"],
        plan_date=state["plan_date"],
        extra_context=json.dumps(extra_context, ensure_ascii=False),
    )
    content = await invoke_structured(SleepPlanContent, prompt, fallback=_rule_based_content(state))
    return {"content": content}


def build():
    graph = StateGraph(SleepPlanState)
    graph.add_node("gather", gather)
    graph.add_node("generate", generate)
    graph.set_entry_point("gather")
    graph.add_edge("gather", "generate")
    graph.add_edge("generate", END)
    return graph.compile()
