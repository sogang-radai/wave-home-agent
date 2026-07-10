"""insight-generation-api.md 의 `/insight/v1/insights` 생성 그래프.

app/graph/report_turn_graph.py 와 동일한 2-노드 gather->generate 패턴을 재사용한다:
에이전트가 db/query·rag/search 툴로 부족한 데이터를 스스로 조회(gather)한 뒤,
그 결과를 근거로 구조화 출력을 생성(generate)한다. sleep/power 리포트와 달리
백엔드가 metrics 를 인라인으로 주지 않으므로 이 패턴이 적합하다.

SURFACE_TABLES/SURFACE_RAG_COLLECTIONS 매핑은 insight-generation-api.md 에 명시되지
않은 추정치다(db-schema.md 의 insight.surface 값과 rag-api.md 의 insight_* 컬렉션
대응 관계를 근거로 구성). 실제 사용 시 팀원 확인 필요.
"""

import json
from datetime import datetime
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph

from app.graph.tool_loop import build_tool_loop
from app.graph.tools import make_query_db_tool, make_rag_search_tool
from app.schemas.insight import GeneratedInsightBatch
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.insight_state import InsightGenerationState


MAX_CONTEXT_ROUNDS = 2

# 사용자가 바로 실행할 수 있는 액션이 없으면 화면이 텍스트만 나열하는 배너로 전락한다 —
# 이 surface 들은 actionable 항목이 최소 1개는 있어야 한다. posture_report 는 요청에 따라
# 잠시 제외(다시 필요해지면 이 set 에 넣기만 하면 된다 — _FALLBACK_ACTIONS 항목은 남겨둠).
REQUIRE_ACTIONABLE_SURFACES = {"sleep_report", "power", "weekly_plan"}
MAX_GENERATE_ATTEMPTS = 2

_ACTIONABLE_REQUIREMENT_TEXT = """
[필수] 이 화면(surface)은 반드시 actionable=true 항목을 최소 1개 포함해야 합니다.
조회된 데이터에서 실행 가능한 신호(반복되는 패턴, 임계치 근접, 습관화 여지 등)를 찾아
actionType(schedule_task 또는 automation_rule)과 그에 맞는 scheduleTaskJson/ruleJson을
실제로 적용 가능한 형태로 채우세요. 다른 항목들은 배너/팁이어도 되지만, 이 하나는
"검토 후 실행" 수준으로 구체적이어야 합니다."""

_RETRY_FEEDBACK_TEXT = """

[재시도] 이전 시도에서 만든 인사이트엔 actionable=true 항목이 하나도 없었습니다.
이번엔 위 [필수] 요구사항을 반드시 지켜서, actionType/scheduleTaskJson(또는 ruleJson)이
채워진 실행형 항목을 최소 1개 포함하세요."""

_FALLBACK_ACTIONS: dict[str, dict[str, Any]] = {
    "sleep_report": {
        "title": "취침 전 루틴 등록",
        "text": "취침 전 스마트폰 사용을 줄이면 입면에 도움이 됩니다. 취침 30분 전 알림을 등록해보세요.",
        "actionType": "schedule_task",
        "category": "mental",
        "task_title": "취침 전 스마트폰 멀리하기",
        "start_minute": 1350,
        "end_minute": 1380,
    },
    "posture_report": {
        "title": "자세 스트레칭 알림 등록",
        "text": "장시간 같은 자세는 뻐근함을 유발할 수 있어요. 아침 스트레칭 알림을 등록해보세요.",
        "actionType": "schedule_task",
        "category": "posture",
        "task_title": "아침 스트레칭",
        "start_minute": 420,
        "end_minute": 435,
    },
    "power": {
        "title": "심야 대기전력 차단 자동화",
        "text": "사용하지 않는 시간대엔 플러그를 자동으로 꺼서 대기전력을 줄일 수 있어요.",
        "actionType": "automation_rule",
        "device_id": 6,
        "rule_name": "심야 대기전력 차단",
        "schedule_time": "01:00",
    },
    "weekly_plan": {
        "title": "다음 주 계획 세우기",
        "text": "일요일 저녁에 잠깐 시간을 내어 다음 주 루틴을 점검하면 목표 달성률이 올라갑니다.",
        "actionType": "schedule_task",
        "category": "life",
        "task_title": "다음 주 계획 세우기",
        "start_minute": 1200,
        "end_minute": 1230,
        "day_of_week": "sun",
    },
}

SURFACE_TABLES: dict[str, set[str]] = {
    "dashboard_banner": {"sleep_report", "power_report", "schedule_task", "alarm"},
    "weekly_plan": {"schedule_task", "sleep_report", "posture_report", "weekly_plan_report"},
    "sleep_report": {"sleep_session", "sleep_stat", "sleep_report"},
    "posture_report": {"gesture_log", "posture_stat", "posture_report"},
    "power": {"power_energy", "power_report"},
}

SURFACE_RAG_COLLECTIONS: dict[str, set[str]] = {
    "dashboard_banner": {"insight_dashboard"},
    "weekly_plan": {"weekly_plan_report", "insight_weekly_plan"},
    "sleep_report": {"sleep_report", "sleep_stat", "insight_sleep"},
    "posture_report": {"posture_report", "insight_posture"},
    "power": {"power_report", "insight_power"},
}

_CONTEXT_SYSTEM_PROMPT = """당신은 WaveHome 인사이트 생성을 돕는 조사자입니다.
주어진 힌트(context)만으로 인사이트를 만들기 부족할 때만 db/query·rag_search 로 추가 조회하세요.
필요 없으면 tool을 호출하지 말고 "충분합니다"라고만 답하세요."""


def _seed_message(state: InsightGenerationState) -> HumanMessage:
    return HumanMessage(
        content=(
            f"surface: {state['surface']}\n"
            f"date: {state['date']}\n"
            f"context: {json.dumps(state.get('context') or {}, ensure_ascii=False)}"
        )
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


def _day_of_week(date: str) -> str:
    return datetime.strptime(date, "%Y-%m-%d").strftime("%a").lower()


def _fallback_actionable_insight(state: InsightGenerationState) -> dict[str, Any]:
    """2번의 generate 시도에도 actionable 항목이 안 나온 REQUIRE_ACTIONABLE_SURFACES 용
    최후 방어선. LLM 이 뭘 생성하든 이 규칙 기반 항목이 "최소 1개 actionable" 계약을
    코드 레벨에서 보장한다."""
    surface = state["surface"]
    spec = _FALLBACK_ACTIONS[surface]
    day = spec.get("day_of_week") or _day_of_week(state["date"])
    base = {
        "surface": surface,
        "kind": "action",
        "date": state["date"],
        "label": None,
        "title": spec["title"],
        "text": spec["text"],
        "actionable": True,
        "actionType": spec["actionType"],
        "ruleJson": None,
        "scheduleTaskJson": None,
        "embedding": None,
    }
    if spec["actionType"] == "schedule_task":
        base["scheduleTaskJson"] = {
            "userId": state["user_id"],
            "title": spec["task_title"],
            "category": spec["category"],
            "scheduleKind": "weekly",
            "dayOfWeek": day,
            "eventDate": None,
            "startMinute": spec["start_minute"],
            "endMinute": spec["end_minute"],
        }
    else:
        base["ruleJson"] = {
            "name": spec["rule_name"],
            "enabled": True,
            "trigger": None,
            "schedule": {"repeat": "daily", "time": spec["schedule_time"]},
            "action": {"deviceId": spec["device_id"], "name": "off", "params": {}},
            "execMode": "repeat",
            "repeatIntervalMs": None,
            "cooldownMs": 0,
        }
    return base


async def gather(state: InsightGenerationState) -> dict[str, Any]:
    surface = state["surface"]
    tools = [
        make_query_db_tool(state["user_id"], allowed_tables=SURFACE_TABLES.get(surface, set())),
        make_rag_search_tool(allowed_collections=SURFACE_RAG_COLLECTIONS.get(surface, set())),
    ]
    loop = build_tool_loop(
        InsightGenerationState,
        tools,
        max_rounds=MAX_CONTEXT_ROUNDS,
        system_prompt_fn=lambda _state: _CONTEXT_SYSTEM_PROMPT,
    )
    result = await loop.ainvoke({"messages": [_seed_message(state)], "rounds": 0})
    return {"messages": result["messages"]}


def _needs_actionable(state: InsightGenerationState) -> bool:
    return state["surface"] in REQUIRE_ACTIONABLE_SURFACES


async def generate(state: InsightGenerationState) -> dict[str, Any]:
    attempt = state.get("generate_attempts", 0)  # 이 호출이 몇 번째 시도인지(0-based)
    extra_context = _extract_tool_results(state.get("messages", []))
    prompt = load_prompt(
        "insight",
        "generate",
        user_id=state["user_id"],
        surface=state["surface"],
        date=state["date"],
        context=json.dumps(state.get("context") or {}, ensure_ascii=False),
        extra_context=json.dumps(extra_context, ensure_ascii=False),
        retry_feedback=_RETRY_FEEDBACK_TEXT if attempt > 0 else "",
        actionable_requirement=_ACTIONABLE_REQUIREMENT_TEXT if _needs_actionable(state) else "",
    )
    batch = await invoke_structured(GeneratedInsightBatch, prompt, fallback=GeneratedInsightBatch(items=[]))
    items = [item.model_dump() for item in batch.items]
    attempts_done = attempt + 1

    if _needs_actionable(state) and not any(item["actionable"] for item in items):
        if attempts_done >= MAX_GENERATE_ATTEMPTS:
            # 재시도 예산 소진 — 규칙 기반 fallback 으로 "최소 1개 actionable" 계약을 강제한다.
            items.append(_fallback_actionable_insight(state))

    return {"items": items, "generate_attempts": attempts_done}


def _should_retry_generate(state: InsightGenerationState) -> str:
    if not _needs_actionable(state):
        return END
    if any(item["actionable"] for item in state.get("items", [])):
        return END
    if state.get("generate_attempts", 0) < MAX_GENERATE_ATTEMPTS:
        return "generate"
    return END


def build():
    graph = StateGraph(InsightGenerationState)
    graph.add_node("gather", gather)
    graph.add_node("generate", generate)
    graph.set_entry_point("gather")
    graph.add_edge("gather", "generate")
    graph.add_conditional_edges("generate", _should_retry_generate, {"generate": "generate", END: END})
    return graph.compile()
