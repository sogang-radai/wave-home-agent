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
# 이 surface 들은 전체 항목이 최소 MIN_TOTAL_ITEMS개, 그중 actionable 항목이 최소
# MIN_ACTIONABLE_ITEMS개는 있어야 한다. posture_report 는 요청에 따라 잠시 제외(다시
# 필요해지면 이 set 에 넣기만 하면 된다 — _FALLBACK_ACTIONS 항목은 남겨둠).
REQUIRE_ACTIONABLE_SURFACES = {"sleep_report", "power", "weekly_plan"}
MAX_GENERATE_ATTEMPTS = 3
MIN_ACTIONABLE_ITEMS = 2
MIN_TOTAL_ITEMS = 4

_ACTIONABLE_REQUIREMENT_TEXT = f"""
[필수] 이 화면(surface)은 전체 인사이트를 최소 {MIN_TOTAL_ITEMS}개 포함해야 하고, 그중
actionable=true 항목이 최소 {MIN_ACTIONABLE_ITEMS}개 이상이어야 합니다. actionable 항목마다
조회된 데이터에서 실행 가능한 신호(반복되는 패턴, 임계치 근접, 습관화 여지 등)를 찾아
actionType(schedule_task 또는 automation_rule)과 그에 맞는 scheduleTaskJson/ruleJson을
실제로 적용 가능한 형태로 채우세요. 나머지 항목은 배너/팁/목표여도 되지만, actionable
항목들은 "검토 후 실행" 수준으로 구체적이어야 합니다."""

_RETRY_FEEDBACK_TEXT = f"""

[재시도] 이전 시도에서 만든 인사이트가 요구사항(전체 {MIN_TOTAL_ITEMS}개 이상, 그중
actionable=true {MIN_ACTIONABLE_ITEMS}개 이상)을 충족하지 못했습니다. 이번엔 위 [필수]
요구사항을 반드시 지켜서 다시 생성하세요."""

# 각 REQUIRE_ACTIONABLE_SURFACES 는 MIN_TOTAL_ITEMS(4)개의 actionable spec 을 갖고 있다 —
# top-up 이 발동하면 이 리스트 전체를 그대로 붙여서 최악의 경우(LLM 이 아무것도 못 만든 경우)
# 에도 actionable/전체 최소치를 한 번에 만족시킨다(부분만 골라 붙이는 계산은 하지 않는다).
# posture_report 는 REQUIRE_ACTIONABLE_SURFACES 에서 잠시 빠져 있지만 다시 켤 때를 대비해
# 마찬가지로 4개를 채워둔다.
_FALLBACK_ACTIONS: dict[str, list[dict[str, Any]]] = {
    "sleep_report": [
        {
            "title": "취침 전 루틴 등록",
            "text": "취침 전 스마트폰 사용을 줄이면 입면에 도움이 됩니다. 취침 30분 전 알림을 등록해보세요.",
            "actionType": "schedule_task",
            "category": "mental",
            "task_title": "취침 전 스마트폰 멀리하기",
            "start_minute": 1350,
            "end_minute": 1380,
            "day_of_week": "mon",
        },
        {
            "title": "취침 조명 자동화 설정",
            "text": "매일 밤 11시에 조명을 자동으로 낮춰 숙면을 도와드릴게요.",
            "actionType": "automation_rule",
            "device_id": 11,
            "rule_name": "취침 조명 자동화",
            "schedule_time": "23:00",
        },
        {
            "title": "규칙적인 기상 알림",
            "text": "매일 같은 시간에 일어나면 수면 리듬을 유지하는 데 도움이 됩니다.",
            "actionType": "schedule_task",
            "category": "mental",
            "task_title": "규칙적인 기상 알림",
            "start_minute": 420,
            "end_minute": 435,
            "day_of_week": "mon",
        },
        {
            "title": "낮잠 자제 알림",
            "text": "오후 낮잠이 길어지면 밤잠에 방해가 될 수 있어요. 낮잠 시간을 알림으로 관리해보세요.",
            "actionType": "schedule_task",
            "category": "mental",
            "task_title": "오후 낮잠 자제",
            "start_minute": 840,
            "end_minute": 855,
            "day_of_week": "mon",
        },
    ],
    "posture_report": [
        {
            "title": "자세 스트레칭 알림 등록",
            "text": "장시간 같은 자세는 뻐근함을 유발할 수 있어요. 아침 스트레칭 알림을 등록해보세요.",
            "actionType": "schedule_task",
            "category": "posture",
            "task_title": "아침 스트레칭",
            "start_minute": 420,
            "end_minute": 435,
            "day_of_week": "mon",
        },
        {
            "title": "점심 후 스트레칭 알림",
            "text": "점심 식사 후 잠깐 스트레칭하면 오후 앉은 자세 부담을 줄일 수 있어요.",
            "actionType": "schedule_task",
            "category": "posture",
            "task_title": "점심 후 스트레칭",
            "start_minute": 780,
            "end_minute": 790,
            "day_of_week": "tue",
        },
        {
            "title": "저녁 스트레칭 알림",
            "text": "하루를 마무리하며 스트레칭하면 다음 날 뻐근함이 줄어듭니다.",
            "actionType": "schedule_task",
            "category": "posture",
            "task_title": "저녁 스트레칭",
            "start_minute": 1140,
            "end_minute": 1155,
            "day_of_week": "wed",
        },
        {
            "title": "주말 자세 점검",
            "text": "주말에 잠깐 시간을 내어 한 주의 자세 습관을 점검해보세요.",
            "actionType": "schedule_task",
            "category": "posture",
            "task_title": "주말 자세 점검",
            "start_minute": 600,
            "end_minute": 615,
            "day_of_week": "sat",
        },
    ],
    "power": [
        {
            "title": "심야 대기전력 차단 자동화",
            "text": "사용하지 않는 시간대엔 플러그를 자동으로 꺼서 대기전력을 줄일 수 있어요.",
            "actionType": "automation_rule",
            "device_id": 6,
            "rule_name": "심야 대기전력 차단",
            "schedule_time": "01:00",
        },
        {
            "title": "전력 사용량 점검 알림",
            "text": "매주 일요일 저녁에 전력 사용량을 점검하면 누진 구간 진입을 미리 대비할 수 있어요.",
            "actionType": "schedule_task",
            "category": "life",
            "task_title": "전력 사용량 점검",
            "start_minute": 1200,
            "end_minute": 1215,
            "day_of_week": "sun",
        },
        {
            "title": "피크 시간대 가전 사용 점검",
            "text": "저녁 피크 시간대 사용량이 몰리면 요금이 늘어날 수 있어요. 사용 시간 분산을 점검해보세요.",
            "actionType": "schedule_task",
            "category": "life",
            "task_title": "피크 시간대 가전 사용 점검",
            "start_minute": 1080,
            "end_minute": 1095,
            "day_of_week": "mon",
        },
        {
            "title": "주방 대기전력 차단 자동화",
            "text": "야간엔 주방 콘센트도 자동으로 꺼서 대기전력을 줄일 수 있어요.",
            "actionType": "automation_rule",
            "device_id": 9,
            "rule_name": "심야 주방 대기전력 차단",
            "schedule_time": "00:30",
        },
    ],
    "weekly_plan": [
        {
            "title": "다음 주 계획 세우기",
            "text": "일요일 저녁에 잠깐 시간을 내어 다음 주 루틴을 점검하면 목표 달성률이 올라갑니다.",
            "actionType": "schedule_task",
            "category": "life",
            "task_title": "다음 주 계획 세우기",
            "start_minute": 1200,
            "end_minute": 1230,
            "day_of_week": "sun",
        },
        {
            "title": "평일 취침 시간 알림 설정",
            "text": "평일 취침 시간을 지키면 주간 목표 달성률이 올라갑니다. 알림을 등록해보세요.",
            "actionType": "schedule_task",
            "category": "life",
            "task_title": "평일 취침 시간 알림",
            "start_minute": 1380,
            "end_minute": 1395,
            "day_of_week": "mon",
        },
        {
            "title": "이번 주 목표 점검",
            "text": "주 중반에 목표 달성 상황을 점검하면 남은 기간을 더 잘 활용할 수 있어요.",
            "actionType": "schedule_task",
            "category": "life",
            "task_title": "주간 목표 점검",
            "start_minute": 420,
            "end_minute": 435,
            "day_of_week": "wed",
        },
        {
            "title": "주말 전 정리 알림",
            "text": "한 주를 마무리하며 미룬 일을 정리하면 주말을 더 여유롭게 보낼 수 있어요.",
            "actionType": "schedule_task",
            "category": "life",
            "task_title": "한 주 마무리 정리",
            "start_minute": 1260,
            "end_minute": 1280,
            "day_of_week": "fri",
        },
    ],
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


def _build_actionable_item(state: InsightGenerationState, spec: dict[str, Any]) -> dict[str, Any]:
    """_FALLBACK_ACTIONS[surface]["actionable"] 의 spec 하나를 GeneratedInsight 모양의
    dict 로 조립한다. 2번의 generate 시도에도 요구 개수를 못 채운 REQUIRE_ACTIONABLE_SURFACES
    용 최후 방어선 — LLM 이 뭘 생성하든 이 규칙 기반 항목들이 최소 개수 계약을 코드 레벨에서
    보장한다."""
    surface = state["surface"]
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


def _top_up_items(state: InsightGenerationState, items: list[dict[str, Any]]) -> None:
    """items 에 surface 의 fallback actionable 리스트(정확히 MIN_TOTAL_ITEMS개) 전체를
    그대로 붙인다. 부분만 골라 붙이면 "몇 개가 모자란지" 계산이 필요해 실수하기 쉬운데,
    리스트 자체가 이미 두 최소치(MIN_ACTIONABLE_ITEMS/MIN_TOTAL_ITEMS)를 넘도록 채워져
    있으므로 무조건 전체를 더하는 쪽이 더 단순하고 안전하다."""
    for spec in _FALLBACK_ACTIONS[state["surface"]]:
        items.append(_build_actionable_item(state, spec))


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

    if _needs_actionable(state) and not _meets_requirements(items) and attempts_done >= MAX_GENERATE_ATTEMPTS:
        # 재시도 예산 소진 — 규칙 기반 fallback 으로 "최소 개수" 계약을 강제한다.
        _top_up_items(state, items)

    return {"items": items, "generate_attempts": attempts_done}


def _meets_requirements(items: list[dict[str, Any]]) -> bool:
    actionable_count = sum(1 for item in items if item["actionable"])
    return actionable_count >= MIN_ACTIONABLE_ITEMS and len(items) >= MIN_TOTAL_ITEMS


def _should_retry_generate(state: InsightGenerationState) -> str:
    if not _needs_actionable(state):
        return END
    if _meets_requirements(state.get("items", [])):
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
