"""goal-coaching 기능(신규)의 목표 코칭 리포트 생성 그래프.

app/graph/weekly_plan_graph.py 의 gather->generate 2노드 패턴을 기본 골격으로 삼되, 그 사이에
결정적 analyze 노드를 하나 더 끼워 넣는다: "최근 30일 완료율/연속일수/추세"는 LLM 이 계산하게
두면 실측으로 자주 틀리므로(app/graph/insight_graph.py 의 코멘트와 동일한 이유), 코드로
직접 집계한 뒤 프롬프트에는 숫자만 주입한다(analyze 는 LLM 을 전혀 호출하지 않는다).

app/graph/insight_graph.py 와 달리 재시도 루프(MAX_GENERATE_ATTEMPTS)는 두지 않는다 - 이
기능은 "actionable 항목 개수 최소치를 반드시 채워야 하는" 화면 계약이 없고, 목표 코칭은
데이터가 부족하면 items 를 비워도 정직한 답이 된다(REQUIRE_ACTIONABLE_SURFACES 에 해당하는
개념이 없음).

GOAL_COACHING_TABLES: RAG 컬렉션은 이 기능이 필요로 하지 않아 rag_search tool 은 gather 의
tool loop 에 포함하지 않는다 - 필요한 건 의미 기반 리포트 검색이 아니라 정확한 최근 30일
행동 로그이고, 그건 gather 에서 결정적으로 조회한다.
"""

import json
from datetime import date, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph

from app.graph.insight_graph import (
    _devices_with_actions,
    _fetch_action_names_by_class,
    _fetch_devices,
    _rulejson_device_ids_to_wire,
    _validate_automation_rules,
)
from app.graph.tool_loop import build_tool_loop
from app.graph.tools import make_query_db_tool
from app.schemas.goal_coaching import GoalCoachingContent, GoalRecommendationItem
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.goal_coaching_state import GoalCoachingState
from app.tools.db_query import DbQuery, query_db


MAX_CONTEXT_ROUNDS = 2
ANALYSIS_WINDOW_DAYS = 30
# 추세(improving/declining) 판정 마진 - 이보다 작은 차이는 "steady"로 본다(노이즈에 흔들리지
# 않기 위한 완충 구간, insight_graph.py 의 여러 임계치 방어선과 같은 철학).
TREND_MARGIN = 0.05
# 이보다 적은 활동일수(actionType 상관없이 이 category 로 뭐라도 로그가 찍힌 날)면 30일
# 서사를 만들기엔 근거가 너무 얇다고 보고 insufficient_data=True 로 표시한다.
MIN_ACTIVE_DAYS = 7

GOAL_COACHING_TABLES: set[str] = {"goal", "user_action_log", "schedule_task"}

_CONTEXT_SYSTEM_PROMPT = """당신은 WaveHome 목표 코칭을 돕는 조사자입니다.
이 목표와 관련해 이미 조회된 최근 30일 user_action_log/schedule_task 데이터 외에 추가로
필요한 정보가 있을 때만 db/query 로 조회하세요. 필요 없으면 tool을 호출하지 말고
"충분합니다"라고만 답하세요."""


def _window(period_start: str) -> tuple[str, str]:
    end = date.fromisoformat(period_start)
    start = end - timedelta(days=ANALYSIS_WINDOW_DAYS)
    return start.isoformat(), end.isoformat()


def _seed_message(state: GoalCoachingState, date_from: str, date_to: str) -> HumanMessage:
    return HumanMessage(
        content=(
            f"목표: {state['goal_title']} (category: {state['category']})\n"
            f"분석 구간: {date_from} ~ {date_to}\n"
            "이미 이 구간의 user_action_log/schedule_task 는 별도로 조회되어 있습니다. "
            "이 목표 분석에 추가로 필요한 정보가 있으면 tool을 호출하세요."
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


async def gather(state: GoalCoachingState) -> dict[str, Any]:
    date_from, date_to = _window(state["period_start"])

    # 30일 윈도우는 LLM 의 tool 호출 판단에 맡기지 않고 여기서 직접 계산해서 넘긴다
    # (app/graph/insight_graph.py 의 _fetch_devices 와 동일하게, analyze 가 반드시 필요로
    # 하는 입력은 tool loop 밖에서 결정적으로 확보한다).
    [action_log_result] = await query_db(
        [
            DbQuery(
                table="user_action_log",
                filter={"userId": state["user_id"], "category": state["category"], "from": date_from, "to": date_to},
            )
        ]
    )
    action_logs = action_log_result.items if action_log_result.error is None else []

    [schedule_task_result] = await query_db(
        [DbQuery(table="schedule_task", filter={"userId": state["user_id"], "category": state["category"]})]
    )
    schedule_tasks = schedule_task_result.items if schedule_task_result.error is None else []

    devices = await _fetch_devices(state["user_id"])
    action_names_by_class = await _fetch_action_names_by_class()

    # LLM 에게 "혹시 더 볼 게 있으면 보라"는 탈출구만 남겨둔다 - 위 결정적 조회로 보통은
    # 충분하므로 max_rounds 를 짧게(2) 둔다.
    tools = [make_query_db_tool(state["user_id"], allowed_tables=GOAL_COACHING_TABLES)]
    loop = build_tool_loop(
        GoalCoachingState,
        tools,
        max_rounds=MAX_CONTEXT_ROUNDS,
        system_prompt_fn=lambda _state: _CONTEXT_SYSTEM_PROMPT,
    )
    result = await loop.ainvoke({"messages": [_seed_message(state, date_from, date_to)], "rounds": 0})

    return {
        "messages": result["messages"],
        "action_logs": action_logs,
        "schedule_tasks": schedule_tasks,
        "devices": devices,
        "action_names_by_class": action_names_by_class,
    }


def _consecutive_streak(sorted_dates_desc: list[str]) -> int:
    """가장 최근 날짜부터 하루씩 거슬러 올라가며 빠짐없이 이어지는 일수를 센다.
    sorted_dates_desc 는 중복 없는 'YYYY-MM-DD' 날짜 문자열의 내림차순 리스트여야 한다."""
    if not sorted_dates_desc:
        return 0
    streak = 1
    current = date.fromisoformat(sorted_dates_desc[0])
    for date_str in sorted_dates_desc[1:]:
        expected_prev = current - timedelta(days=1)
        if date.fromisoformat(date_str) != expected_prev:
            break
        streak += 1
        current = expected_prev
    return streak


def _completion_rate(logs: list[dict[str, Any]]) -> "float | None":
    completed = sum(1 for a in logs if a.get("actionType") == "schedule_task_completed")
    uncompleted = sum(1 for a in logs if a.get("actionType") == "schedule_task_uncompleted")
    denom = completed + uncompleted
    return (completed / denom) if denom > 0 else None


def analyze(state: GoalCoachingState) -> dict[str, Any]:
    """순수 파이썬 집계 - LLM 을 호출하지 않는다. gather 가 결정적으로 조회해 둔
    state["action_logs"]만 입력으로 쓴다(tool loop 메시지의 JSON 문자열을 다시 파싱하지
    않기 위해 - app/graph/insight_graph.py 의 devices/action_names_by_class 와 동일한 이유)."""
    logs = state.get("action_logs", [])
    date_from, date_to = _window(state["period_start"])

    completed = sum(1 for a in logs if a.get("actionType") == "schedule_task_completed")
    uncompleted = sum(1 for a in logs if a.get("actionType") == "schedule_task_uncompleted")
    denom = completed + uncompleted
    completion_rate = (completed / denom) if denom > 0 else None

    completed_dates = sorted(
        {str(a["occurredAt"])[:10] for a in logs if a.get("actionType") == "schedule_task_completed"},
        reverse=True,
    )
    streak_days = _consecutive_streak(completed_dates)

    # 30일 구간을 절반으로 나눠(최근 15일 vs 이전 15일) 완료율 추세를 비교한다. 자정 경계는
    # 'YYYY-MM-DD' 문자열 비교로 충분하다(occurredAt 이 'YYYY-MM-DD HH:MM:SS' 이므로 앞 10자만
    # 비교해도 사전식 정렬이 날짜 정렬과 일치한다).
    mid = (date.fromisoformat(date_to) - timedelta(days=ANALYSIS_WINDOW_DAYS // 2)).isoformat()
    recent_logs = [a for a in logs if str(a["occurredAt"])[:10] >= mid]
    previous_logs = [a for a in logs if str(a["occurredAt"])[:10] < mid]
    recent_rate = _completion_rate(recent_logs)
    previous_rate = _completion_rate(previous_logs)
    if recent_rate is None or previous_rate is None:
        trend = "steady"
    elif recent_rate - previous_rate >= TREND_MARGIN:
        trend = "improving"
    elif recent_rate - previous_rate <= -TREND_MARGIN:
        trend = "declining"
    else:
        trend = "steady"

    active_days = {str(a["occurredAt"])[:10] for a in logs}
    insufficient_data = len(active_days) < MIN_ACTIVE_DAYS

    stats = {
        "periodStart": date_from,
        "periodEnd": date_to,
        "completionRate": completion_rate,
        "streakDays": streak_days,
        "trend": trend,
        "completedCount": completed,
        "uncompletedCount": uncompleted,
        "activeDays": len(active_days),
        "insufficientData": insufficient_data,
    }
    return {"stats": stats}


def _fallback_content(state: GoalCoachingState) -> GoalCoachingContent:
    """LLM 이 없거나(no_real_llm 테스트 픽스처) 두 번의 시도가 모두 실패했을 때 쓰는 규칙
    기반 폴백 - insight_graph.py 의 _FALLBACK_ACTIONS 와 같은 철학으로, 빈 응답 대신 실제
    집계된 숫자를 그대로 문장에 박아 넣어 "결정적이지만 내용은 있는" 응답을 만든다."""
    stats = state.get("stats", {})
    goal_title = state["goal_title"]

    if stats.get("insufficientData"):
        category = state.get("category", "life")
        starter_title = f"「{goal_title}」 첫 실천 알림"
        return GoalCoachingContent(
            pastSummary=(
                f"「{goal_title}」 목표를 새로 설정했어요. 아직 관련 실천 기록이 없어"
                f"(활동일 {stats.get('activeDays', 0)}일) 지난 성과를 숫자로 말하기는 어려워요."
                " 아래 첫걸음부터 기록해 보면 다음 코칭이 훨씬 구체적해져요."
            ),
            projection=(
                f"「{goal_title}」을 주간 일정으로 등록해 실천을 쌓아 보세요."
                " 기록이 모이면 완료율과 다음 달 전망을 알려드릴게요."
            ),
            projectedMetrics=dict(stats),
            items=[
                GoalRecommendationItem(
                    kind="action",
                    title=starter_title,
                    text=f"「{goal_title}」을 기억하기 쉬운 요일·시간에 한 번 넣어 두세요.",
                    actionable=True,
                    actionType="schedule_task",
                    scheduleTaskJson={
                        "title": starter_title,
                        "dayOfWeek": "mon",
                        "scheduleKind": "weekly",
                        "category": category,
                    },
                ),
                GoalRecommendationItem(
                    kind="tip",
                    title="작게 시작하기",
                    text=f"처음 일주일은 「{goal_title}」을 완벽히 지키기보다, 실천 여부만 체크해도 충분해요.",
                    actionable=False,
                ),
            ],
        )

    rate = stats.get("completionRate")
    rate_text = f"{round(rate * 100)}%" if rate is not None else "알 수 없음"
    trend = stats.get("trend", "steady")
    trend_text = {"improving": "점점 나아지고 있어요", "declining": "조금씩 흔들리고 있어요", "steady": "비슷한 수준을 유지하고 있어요"}[trend]
    streak = stats.get("streakDays", 0)

    past_summary = (
        f"최근 30일간 '{goal_title}' 관련 일정을 {stats.get('completedCount', 0)}번 완료했고,"
        f" 완료율은 {rate_text}였어요. 최근 연속 {streak}일 동안 실천했고, 추세는 {trend_text}."
    )
    if trend == "improving":
        projection = "이대로면 다음 달은 지금보다 더 안정적으로 목표를 지킬 수 있을 것 같아요."
    elif trend == "declining":
        projection = "이대로면 다음 달은 실천이 더 느슨해질 수 있어요. 지금 습관을 다시 다잡아보세요."
    else:
        projection = "이대로면 다음 달도 지금과 비슷한 흐름으로 이어질 것 같아요."

    items = [
        GoalRecommendationItem(
            kind="tip",
            title="꾸준함이 핵심이에요",
            text=f"'{goal_title}' 목표는 완료율보다 연속 실천일이 더 중요해요. 지금의 {streak}일 기록을 이어가보세요.",
            actionable=False,
        )
    ]
    return GoalCoachingContent(pastSummary=past_summary, projection=projection, projectedMetrics=dict(stats), items=items)


async def generate(state: GoalCoachingState) -> dict[str, Any]:
    stats = state.get("stats", {})
    devices = state.get("devices", [])
    action_names_by_class = state.get("action_names_by_class", {})
    extra_context = _extract_tool_results(state.get("messages", []))

    prompt = load_prompt(
        "goal_coaching",
        "generate",
        user_id=state["user_id"],
        goal_title=state["goal_title"],
        category=state["category"],
        period_start=state["period_start"],
        stats=json.dumps(stats, ensure_ascii=False),
        schedule_tasks=json.dumps(state.get("schedule_tasks", []), ensure_ascii=False),
        devices=json.dumps(_devices_with_actions(devices, action_names_by_class), ensure_ascii=False),
        extra_context=json.dumps(extra_context, ensure_ascii=False),
    )
    content = await invoke_structured(GoalCoachingContent, prompt, fallback=_fallback_content(state))

    # automation_rule 사후 검증은 app/graph/insight_graph.py 의 _validate_automation_rules 를
    # 그대로 재사용한다 - 그 함수는 list[dict] 의 "actionType"/"ruleJson"/"actionable" 키만
    # 보고 동작해서(GeneratedInsight 전용 타입에 의존하지 않음) GoalRecommendationItem 을
    # model_dump() 한 dict 를 그대로 넣어도 셰이프가 맞는다 - 별도 shim 이 필요 없었다.
    items = [item.model_dump() for item in content.items]
    items = _validate_automation_rules(items, devices, action_names_by_class)
    items = _rulejson_device_ids_to_wire(items, devices)

    # projectedMetrics 는 LLM 이 옮겨 적은 값이 아니라 analyze()가 계산한 canonical 값으로
    # 항상 덮어쓴다 - 프롬프트에 "그대로 옮겨 담으라"고 지시해도 경량 모델은 반올림하거나
    # 다른 키를 섞어 넣을 수 있어(insight_graph.py 와 동일한 "LLM 계산을 믿지 않는다" 철학),
    # 최종적으로 내보내는 수치의 정확성은 코드가 보장한다.
    metrics = {
        "completionRate": stats.get("completionRate"),
        "trend": stats.get("trend"),
        "streakDays": stats.get("streakDays"),
        "insufficientData": bool(stats.get("insufficientData")),
        "activeDays": stats.get("activeDays", 0),
    }
    content = content.model_copy(
        update={
            "items": [GoalRecommendationItem(**item) for item in items],
            "projectedMetrics": metrics,
        }
    )
    return {"content": content}


def build():
    graph = StateGraph(GoalCoachingState)
    graph.add_node("gather", gather)
    graph.add_node("analyze", analyze)
    graph.add_node("generate", generate)
    graph.set_entry_point("gather")
    graph.add_edge("gather", "analyze")
    graph.add_edge("analyze", "generate")
    graph.add_edge("generate", END)
    return graph.compile()
