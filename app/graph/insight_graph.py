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
from typing import Any, Optional

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph

from app.graph.tool_loop import build_tool_loop
from app.graph.tools import make_query_db_tool, make_rag_search_tool
from app.schemas.insight import GeneratedInsightBatch
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.insight_state import InsightGenerationState
from app.tools import devices_internal
from app.tools.db_query import DbQuery, query_db
from app.tools.errors import InternalApiError


MAX_CONTEXT_ROUNDS = 2

# 사용자가 바로 실행할 수 있는 액션이 없으면 화면이 텍스트만 나열하는 배너로 전락한다 —
# 이 surface 들은 전체 항목이 최소 MIN_TOTAL_ITEMS개, 그중 actionable 항목으로
# schedule_task 최소 1개·automation_rule 최소 1개가 각각 있어야 한다("actionable 아무거나
# 2개"가 아니라 두 actionType 이 골고루 있어야 화면이 다양해진다). sleep_report/power 는
# 아래 EXACT_COUNT_SURFACES 의 "정확히 action 2개 + tip 2개" 계약으로 옮겨갔다. posture_report
# 는 요청에 따라 잠시 제외(다시 필요해지면 이 set 에 넣기만 하면 된다 — _FALLBACK_ACTIONS
# 항목은 남겨둠).
REQUIRE_ACTIONABLE_SURFACES = {"weekly_plan"}
MAX_GENERATE_ATTEMPTS = 3
MIN_TOTAL_ITEMS = 4

# sleep_report/power 는 "카드가 정확히 4장(action 2 + tip 2)"이어야 하는 화면이다 -
# REQUIRE_ACTIONABLE_SURFACES 의 "최소 개수" 계약과 달리 초과분(goal 항목 포함)도
# 잘라내고, kind 별로 정확한 개수를 강제한다. actionType 다양성(schedule_task/
# automation_rule 각 1개 이상)은 요구하지 않는다 - 사용자가 요청한 건 개수 계약뿐이다.
EXACT_ACTION_COUNT = 2
EXACT_TIP_COUNT = 2
EXACT_COUNT_SURFACES = {"sleep_report", "power"}

# device-tool-api.md 클래스별 레퍼런스 표 기준 Actionable 이 없는 클래스(카메라·레이더) —
# automation_rule 의 action 대상으로 고르면 안 된다.
_NON_ACTIONABLE_DEVICE_CLASSES = {"srs_r4sn", "reolink_e1_pro", "droid_cam"}

# surface 별로 automation_rule 폴백을 만들 때 우선적으로 고를 장치 클래스(있으면 이 순서로,
# 없으면 Actionable 한 아무 장치나). 완전히 하드코딩된 deviceId 대신 "이 surface 라면 보통
# 이런 종류의 장치를 자동화하고 싶을 것"이라는 클래스 힌트만 남겨서, 실제 등록된 장치
# 목록에서 매 실행마다 동적으로 고른다.
_PREFERRED_DEVICE_CLASSES: dict[str, list[str]] = {
    "sleep_report": ["philips_wiz_e29_color", "philips_wiz_e29_white"],
    "power": ["tuya_ep2h"],
    "weekly_plan": ["philips_wiz_e29_color", "philips_wiz_e29_white", "tuya_ep2h"],
}

_ACTIONABLE_REQUIREMENT_TEXT = f"""
[필수] 이 화면(surface)은 전체 인사이트를 최소 {MIN_TOTAL_ITEMS}개 포함해야 하고, 그중
actionable=true 항목으로 actionType="schedule_task" 가 최소 1개, actionType="automation_rule"
이 최소 1개는 있어야 합니다. actionable 항목마다 조회된 데이터에서 실행 가능한 신호(반복되는
패턴, 임계치 근접, 습관화 여지 등)를 찾아 그에 맞는 scheduleTaskJson/ruleJson을 실제로 적용
가능한 형태로 채우세요. automation_rule 의 ruleJson.action.deviceId 는 반드시 [등록된 장치
목록]에 실제로 나온 device.id 값만 쓰세요 - 목록에 없으면 절대 지어내지 말고 대신
actionType="schedule_task" 로 대체하세요. 나머지 항목은 배너/팁/목표여도 되지만, actionable
항목들은 "검토 후 실행" 수준으로 구체적이어야 합니다."""

_RETRY_FEEDBACK_TEXT = f"""

[재시도] 이전 시도에서 만든 인사이트가 요구사항(전체 {MIN_TOTAL_ITEMS}개 이상, 그중
actionable=true 항목으로 schedule_task 1개 이상·automation_rule 1개 이상)을 충족하지
못했습니다. 이번엔 위 [필수] 요구사항을 반드시 지켜서 다시 생성하세요."""

_EXACT_COUNT_REQUIREMENT_TEXT = f"""
[필수] 이 화면(surface)은 반드시 kind="action"(actionable=true) 항목 정확히 2개 -
actionType="automation_rule" 1개와 actionType="schedule_task" 1개 - 와 kind="tip"
항목 정확히 {EXACT_TIP_COUNT}개, 총 4개만 생성하세요(더 많거나 적으면 안 되고, action
두 개가 같은 actionType 이어도 안 됩니다 - 반드시 하나씩 서로 다르게).
kind="goal" 항목은 이 화면에서 만들지 마세요 - 만들어도 그대로 버려집니다.
automation_rule 항목은 ruleJson 을, schedule_task 항목은 scheduleTaskJson 을 실제로
적용 가능한 형태로 채우세요(automation_rule 의 ruleJson.action.deviceId 는 반드시
[등록된 장치 목록]에 실제로 나온 device.id 값만 쓰세요). tip 항목은 actionable=false 로
두고 actionType/ruleJson/scheduleTaskJson 은 모두 null 로 두세요."""

_EXACT_COUNT_RETRY_FEEDBACK_TEXT = f"""

[재시도] 이전 시도에서 만든 인사이트가 요구사항(automation_rule 액션 1개, schedule_task
액션 1개, tip 정확히 {EXACT_TIP_COUNT}개)을 충족하지 못했습니다. 이번엔 위 [필수]
요구사항을 반드시 지켜서 다시 생성하세요."""

# 각 REQUIRE_ACTIONABLE_SURFACES 는 MIN_TOTAL_ITEMS(4)개 이상의 actionable spec 을 갖고
# 있고, 그중 schedule_task/automation_rule 이 각각 최소 1개씩 있다 — top-up 이 발동하면 이
# 리스트 전체를 그대로 붙여서 최악의 경우(LLM 이 아무것도 못 만든 경우)에도 두 actionType의
# 최소치를 한 번에 만족시킨다. automation_rule spec 은 deviceId 를 갖고 있지 않다 - 실행
# 시점에 _pick_device_id() 로 실제 등록된 장치에서 동적으로 고른다(적합한 장치가 하나도
# 없으면 그 spec 은 건너뛴다 - 존재하지 않는 id 를 내보내느니 항목 수를 줄이는 쪽을 택함).
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
        {
            "title": "주말 저녁 조명 자동화",
            "text": "주말 저녁 시간에 맞춰 조명을 자동으로 조절해 한 주를 편안하게 마무리해보세요.",
            "actionType": "automation_rule",
            "rule_name": "주말 저녁 조명 자동화",
            "schedule_time": "20:00",
        },
    ],
}

# EXACT_COUNT_SURFACES 전용 tip fallback — _FALLBACK_ACTIONS 와 달리 actionable 이
# 아니므로 scheduleTaskJson/ruleJson 조립이 필요 없다. top-up 이 tip 부족분을 채울 때만
# 쓰인다(정확히 EXACT_TIP_COUNT 개까지만).
_FALLBACK_TIPS: dict[str, list[dict[str, str]]] = {
    "sleep_report": [
        {
            "title": "취침 전 카페인 피하기",
            "text": "오후 늦게 마시는 카페인은 입면을 늦출 수 있어요. 저녁 이후엔 되도록 피해보세요.",
        },
        {
            "title": "침실 온도 낮추기",
            "text": "약간 서늘한 침실 온도가 더 깊은 잠에 도움이 됩니다.",
        },
    ],
    "power": [
        {
            "title": "대기전력 확인하기",
            "text": "사용하지 않는 가전도 플러그에 꽂혀 있으면 대기전력을 소모해요. 가끔 점검해보세요.",
        },
        {
            "title": "피크 시간대 분산 사용",
            "text": "여러 가전을 동시에 쓰기보다 시간을 나눠 사용하면 순간 사용량을 줄일 수 있어요.",
        },
    ],
}

SURFACE_TABLES: dict[str, set[str]] = {
    "dashboard_banner": {"sleep_report", "power_report", "schedule_task", "alarm", "device"},
    "weekly_plan": {"schedule_task", "sleep_report", "posture_report", "weekly_plan_report", "device"},
    "sleep_report": {"sleep_session", "sleep_stat", "sleep_report", "device"},
    "posture_report": {"gesture_log", "posture_stat", "posture_report", "device"},
    "power": {"power_energy", "power_report", "device"},
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

# dashboard_banner 는 집 전체를 총괄하는 홈 화면 배너다 - 한 영역(수면이면 수면만)에 치우치지
# 않도록 gather 단계에서 수면·전력 데이터를 둘 다 확인하도록 명시적으로 유도한다(그 외
# surface는 원래 자기 영역 하나만 보면 되므로 기본 프롬프트로 충분).
_DASHBOARD_CONTEXT_SYSTEM_PROMPT = """당신은 WaveHome 홈 화면 배너를 위해 집 전체 상태를 살피는
조사자입니다. 이 배너는 수면 하나만 다루는 게 아니라 수면·전력 등 집 전체를 총괄하는 메시지이므로,
db/query 로 최근 sleep_report 와 power_report 를 모두 확인해 그중 오늘 언급할 가치가 있는 신호를
찾으세요(하나만 조회하고 멈추지 마세요). 이미 주어진 힌트(context)만으로 충분하면 tool을 호출하지
말고 "충분합니다"라고만 답하세요."""


def _context_system_prompt(surface: str) -> str:
    if surface == "dashboard_banner":
        return _DASHBOARD_CONTEXT_SYSTEM_PROMPT
    return _CONTEXT_SYSTEM_PROMPT


# surface 별 text 분량 가이드. dashboard_banner 는 홈 화면에 단독 배너(헤드라인+본문)로 노출되므로
# 프런트 목업(dashboardInsightData.js)처럼 "무슨 변화가 있었는지 근거 → 그 근거가 된 습관 →
# 지금 습관을 유지/개선하면 기대할 수 있는 효과" 3단 구성의 3~4문장을 요구한다. 그 외 surface
# 는 카드 목록으로 여러 개가 함께 노출되므로 기존처럼 1~2문장으로 짧게 유지한다.
_DEFAULT_LENGTH_GUIDANCE = "text: 1~2문장 본문으로 간결하게 작성하세요."
_LENGTH_GUIDANCE_BY_SURFACE: dict[str, str] = {
    "dashboard_banner": (
        "text: 3~4문장으로 구체적으로 작성하세요. 이 배너는 수면·전력 등 집 전체를 총괄하는 오늘의 "
        "한 마디입니다 - 여러 영역 중 하나만 편협하게 다루지 말고, 조회된 데이터 중 오늘 가장 눈에 "
        "띄는 신호(수면일 수도, 전력일 수도, 여러 영역이 겹친 패턴일 수도 있습니다)를 골라 "
        "(1) 무슨 변화·패턴이 있었는지 근거를 제시하고, (2) 그 근거가 된 습관이나 조건을 언급한 뒤, "
        "(3) 지금의 습관을 유지하거나 개선하면 어떤 효과를 기대할 수 있는지로 마무리하세요. "
        "조회되지 않은 수치는 여전히 지어내지 말고, 대신 정성적인 표현으로 서술하세요."
    ),
}

# dashboard_banner 는 홈 화면 배너 전용 문구다 - 사용자가 승인/거절할 수 있는 카드 UI가 없으므로
# (프런트에 그런 화면 자체가 없음) actionable/automation_rule/schedule_task 를 절대 만들지
# 않는다. 순수 안내 문구 1개만 생성한다.
_NARRATIVE_ONLY_SURFACES = {"dashboard_banner"}

_DEFAULT_ACTIONABLE_GUIDANCE = (
    "actionable=true 인 경우에만 actionType 을 schedule_task|automation_rule|reservation 중 "
    "하나로 채우고, actionType=\"schedule_task\" 면 scheduleTaskJson 을, actionType="
    "\"automation_rule\" 이면 ruleJson 을 실제로 적용 가능한 형태로 채우세요(모르면 "
    "actionable=false 로 두세요)."
)
_NARRATIVE_ONLY_ACTIONABLE_GUIDANCE = (
    "이 화면은 순수 안내 문구 전용입니다 - actionable 은 항상 false 로, actionType/ruleJson/"
    "scheduleTaskJson 은 항상 null 로 두세요. 자동화나 예약을 제안하지 마세요."
)

_DEFAULT_ITEM_COUNT_GUIDANCE = "items 는 보통 1~3개로 제한하되, 아래 [필수] 요구사항이 있으면 그 최소 개수를 우선하세요."
_NARRATIVE_ONLY_ITEM_COUNT_GUIDANCE = "items 는 정확히 1개만 생성하세요(오늘의 배너 문구 하나)."
_EXACT_COUNT_ITEM_COUNT_GUIDANCE = (
    f"items 는 정확히 {EXACT_ACTION_COUNT + EXACT_TIP_COUNT}개만 생성하세요(kind=\"action\" 중 "
    f"actionType=\"automation_rule\" 1개 + actionType=\"schedule_task\" 1개 + kind=\"tip\" "
    f"{EXACT_TIP_COUNT}개, 그 이상도 이하도 안 됩니다)."
)


def _length_guidance(surface: str) -> str:
    return _LENGTH_GUIDANCE_BY_SURFACE.get(surface, _DEFAULT_LENGTH_GUIDANCE)


def _actionable_guidance(surface: str) -> str:
    if surface in _NARRATIVE_ONLY_SURFACES:
        return _NARRATIVE_ONLY_ACTIONABLE_GUIDANCE
    return _DEFAULT_ACTIONABLE_GUIDANCE


def _item_count_guidance(surface: str) -> str:
    if surface in _NARRATIVE_ONLY_SURFACES:
        return _NARRATIVE_ONLY_ITEM_COUNT_GUIDANCE
    if surface in EXACT_COUNT_SURFACES:
        return _EXACT_COUNT_ITEM_COUNT_GUIDANCE
    return _DEFAULT_ITEM_COUNT_GUIDANCE


def _force_narrative_only(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """LLM 이 프롬프트를 무시하고 actionable 항목을 만들 수 있으므로(실측: automation_rule
    검증에서도 같은 패턴 확인됨) 코드 레벨에서 최종적으로 강제한다 - dashboard_banner 는
    승인/거절 UI 자체가 프런트에 없으므로 actionable 항목을 내보내면 조용히 버려질 뿐이다.
    items 도 정확히 1개로 자른다(그 이상은 화면에 노출될 곳이 없다)."""
    forced = []
    for item in items[:1]:
        item = dict(item)
        item["actionable"] = False
        item["actionType"] = None
        item["ruleJson"] = None
        item["scheduleTaskJson"] = None
        forced.append(item)
    return forced


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


def _actionable_devices(devices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [d for d in devices if d.get("class") not in _NON_ACTIONABLE_DEVICE_CLASSES]


def _pick_device_id(devices: list[dict[str, Any]], surface: str) -> Optional[int]:
    """automation_rule 폴백용으로 surface 에 맞는 실제 장치 id 하나를 고른다.
    선호 클래스(_PREFERRED_DEVICE_CLASSES)를 우선 찾고, 없으면 Actionable 한 아무
    장치나 첫 번째를 쓴다. 그마저 없으면 None(호출자가 해당 spec 을 건너뛴다)."""
    candidates = _actionable_devices(devices)
    for class_name in _PREFERRED_DEVICE_CLASSES.get(surface, []):
        for device in candidates:
            if device.get("class") == class_name:
                return device.get("id")
    return candidates[0]["id"] if candidates else None


def _devices_with_actions(
    devices: list[dict[str, Any]], action_names_by_class: dict[str, set[str]]
) -> list[dict[str, Any]]:
    """프롬프트에 보여줄 장치 목록에 클래스별 실제 action 이름을 인라인으로 붙인다 -
    LLM 이 "이 장치로 뭘 할 수 있는지" 를 바로 보고 automation_rule 을 짓게 하기 위함
    (그전에는 device.class 문자열만 보고 action 이름을 추측했다: 실측으로 tuya_ep2h 에
    존재하지 않는 "turn_off" 를 지어낸 적이 있다 - 진짜 이름은 on/off/toggle)."""
    annotated = []
    for device in _actionable_devices(devices):
        item = dict(device)
        item["actions"] = sorted(action_names_by_class.get(device.get("class"), set()))
        annotated.append(item)
    return annotated


def _validate_automation_rules(
    items: list[dict[str, Any]],
    devices: list[dict[str, Any]],
    action_names_by_class: dict[str, set[str]],
) -> list[dict[str, Any]]:
    """LLM 이 만든 automation_rule 항목을 사후 검증한다. gather 에서 device 목록을 결정적으로
    조회해도 LLM 이 그 목록을 무시하고 지어낼 수 있으므로(실측: 3번 중 1번) 코드 레벨
    최후 방어선으로 여기서 최종적으로 걸러낸다. 세 가지를 확인한다:
    1) ruleJson.action.deviceId 가 실제 조작 가능한 장치인지
    2) trigger/schedule 중 최소 하나는 있는지 - device-tool-api.md 설계원칙 2: "trigger 만
       있으면 자동화, schedule 만 있으면 예약, 둘 다 없으면 무효". 실측으로 둘 다 null 인
       룰이 실제로 생성된 적이 있다(백엔드에 그대로 보내면 거부될 무효한 룰).
    3) ruleJson.action.name 이 그 장치 class 에 실제로 존재하는 action 인지 - 실측으로
       tuya_ep2h 에 없는 "turn_off" 를 지어낸 적이 있다(진짜: on/off/toggle). 이건 룰
       생성 API(POST /internal/v1/rules) 자체는 막지 않고 그대로 201 을 반환하지만,
       실행 시점에 Actionable::invoke() 가 그 이름을 못 찾아 조용히 실패한다.
    셋 중 하나라도 실패하면 actionable=false 로 강등한다 - 화면에는 "실행 가능"이라고 보여
    주면서 실제로는 적용이 안 되는 항목을 내보내느니, 항목 수를 줄이는 쪽을 택한다."""
    valid_ids = {device["id"] for device in _actionable_devices(devices)}
    class_by_id = {device["id"]: device.get("class") for device in devices}
    # action_names_by_class 조회 자체가 실패해서 완전히 비어 있으면(예: device-classes 호출
    # 예외) "모른다"는 뜻이지 "다 틀렸다"는 뜻이 아니다 - 이 경우엔 이름 검사를 건너뛴다.
    # 그러지 않으면 조회 실패 한 번으로 모든 automation_rule 이 통째로 걸러진다.
    enforce_action_names = bool(action_names_by_class)
    for item in items:
        if item.get("actionType") != "automation_rule" or not item.get("ruleJson"):
            continue
        rule = item["ruleJson"]
        if not isinstance(rule, dict):
            item["actionable"] = False
            item["actionType"] = None
            item["ruleJson"] = None
            continue
        action = rule.get("action") or {}
        # LLM 이 action 을 객체 대신 문자열로 내는 경우가 있다 — .get 크래시 대신 강등.
        if not isinstance(action, dict):
            item["actionable"] = False
            item["actionType"] = None
            item["ruleJson"] = None
            continue
        # CreateRuleRequest.name 은 필수 필드지만(rules_internal.py) LLM이 종종 통째로
        # 빠뜨림, 이미 만들어둔 item.title 이 사람이 읽는 이름이므로,
        # 없는 값을 새로 지어내는 게 아니라 이미 생성된 값을 그대로 옮기는 것뿐이다.
        # (actionable=false로 강등하는 대신 이렇게 메꾸는 이유: title이 있으면 100%
        # 복구 가능한 결측이라 항목을 통째로 버릴 이유가 없다.)
        if not isinstance(rule.get("name"), str) or not rule["name"].strip():
            rule["name"] = (item.get("title") or "").strip() or "자동화 규칙"
        device_id = action.get("deviceId")
        action_name = action.get("name")
        has_trigger = bool(rule.get("trigger"))
        has_schedule = bool(rule.get("schedule"))
        valid_action_name = (
            not enforce_action_names
            or action_name in action_names_by_class.get(class_by_id.get(device_id), set())
        )
        if device_id not in valid_ids or not (has_trigger or has_schedule) or not valid_action_name:
            item["actionable"] = False
            item["actionType"] = None
            item["ruleJson"] = None
    return items


def _rulejson_device_ids_to_wire(
    items: list[dict[str, Any]], devices: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """automation_rule 의 ruleJson.action.deviceId 를 (내부 규약인 int) 에서 실제 wire
    포맷인 16자리 hex 외부 id 로 바꾼다 - /internal/v1/rules 는 문자열이 아니면 즉시
    400 INVALID_REQUEST 로 거부한다(rule_store.cpp).

    app/tools/device_id.py 의 device_id_to_hex()(zero-pad 공식, 예: 4 -> "0000000000000004")
    는 쓰지 않는다 - 실측 결과 real backend 의 device.externalId 는 정수 id로부터 계산되는
    값이 아니라 device_list.json 에 박힌 임의의 64bit 값이다(예: id=4 -> "6b0f3e8a92c47d15").
    zero-pad 공식으로 만든 값은 rules 생성 API 는 그냥 문자열이라 받아주지만(201), 실행
    시점에 trigger_manager.cpp/action_queue.cpp 가 dev::parseDeviceID() 로 그 문자열을 정수로
    파싱해 deviceManager 에서 직접 찾기 때문에(DB 폴백 조회 없음) 못 찾아서 자동화가 조용히
    실행되지 않는다(직접 재현 확인). 그래서 db/query 가 이미 돌려준 실제 device.wireId 를
    그대로 쓴다. 매핑에 없으면(예: mock 모드처럼 wireId 필드 자체가 없는 경우) 원래 int
    를 그대로 둔다 - 뭘 넣어도 확실하지 않을 땐 지어내지 않는다.

    device 필드명은 real backend db_query_store.cpp 기준 "wireId"다(예전에는 "externalId"인
    device.external_id DB 컬럼을 그대로 내려줬으나, wireId 로 이름이 바뀌고 db_id 로부터
    계산되는 값으로 바뀌었다 — 2026-07-11 리네임, db_query_store.cpp 커밋 34e65bd 참고)."""
    external_id_by_id = {device["id"]: device.get("wireId") for device in devices}
    for item in items:
        rule = item.get("ruleJson")
        if not rule:
            continue
        device_id = (rule.get("action") or {}).get("deviceId")
        external_id = external_id_by_id.get(device_id)
        if isinstance(device_id, int) and external_id:
            rule["action"]["deviceId"] = external_id
    return items


def _build_actionable_item(
    state: InsightGenerationState, spec: dict[str, Any], device_id: Optional[int] = None
) -> dict[str, Any]:
    """_FALLBACK_ACTIONS[surface] 의 spec 하나를 GeneratedInsight 모양의 dict 로 조립한다.
    MAX_GENERATE_ATTEMPTS 번의 generate 시도에도 요구 개수/actionType 구성을 못 채운
    REQUIRE_ACTIONABLE_SURFACES 용 최후 방어선 — LLM 이 뭘 생성하든 이 규칙 기반 항목들이
    최소 계약을 코드 레벨에서 보장한다. automation_rule spec 은 device_id 인자로 실제
    장치 id 를 받아야 한다(없으면 호출하지 말 것 - _top_up_items 가 그 필터링을 한다)."""
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
            "action": {"deviceId": device_id, "name": "off", "params": {}},
            "execMode": "repeat",
            "repeatIntervalMs": None,
            "cooldownMs": 0,
        }
    return base


def _build_tip_item(state: InsightGenerationState, spec: dict[str, str]) -> dict[str, Any]:
    """_FALLBACK_TIPS[surface] 의 spec 하나를 GeneratedInsight 모양의 dict 로 조립한다 -
    _build_actionable_item 과 달리 actionable=False 라 scheduleTaskJson/ruleJson 조립이
    필요 없다."""
    return {
        "surface": state["surface"],
        "kind": "tip",
        "date": state["date"],
        "label": None,
        "title": spec["title"],
        "text": spec["text"],
        "actionable": False,
        "actionType": None,
        "ruleJson": None,
        "scheduleTaskJson": None,
        "embedding": None,
    }


def _finalize_exact_counts(items: list[dict[str, Any]], surface: str) -> list[dict[str, Any]]:
    """EXACT_COUNT_SURFACES 는 정확히 automation_rule 액션 1개 + schedule_task 액션 1개 +
    tip {EXACT_TIP_COUNT}개만 나가야 한다("정해진 개수만큼씩", actionType 도 하나씩 서로
    달라야 함) - 초과분(goal 항목, 같은 actionType 이 중복된 항목 포함)은 잘라내고, 각
    actionType/kind 별로 처음 1(또는 N)개만 남긴다. _validate_automation_rules 로 검증을
    먼저 끝낸 뒤에 호출해야 한다 - 강등된 automation_rule 이 action 슬롯을 무효한 채로
    차지하지 않게 하기 위해서다. 다른 surface 에는 영향 없음(그대로 반환)."""
    if surface not in EXACT_COUNT_SURFACES:
        return items
    rule_actions = [
        item for item in items
        if item.get("kind") == "action" and item.get("actionable") and item.get("actionType") == "automation_rule"
    ]
    task_actions = [
        item for item in items
        if item.get("kind") == "action" and item.get("actionable") and item.get("actionType") == "schedule_task"
    ]
    tips = [item for item in items if item.get("kind") == "tip"]
    return rule_actions[:1] + task_actions[:1] + tips[:EXACT_TIP_COUNT]


def _top_up_items(
    state: InsightGenerationState, items: list[dict[str, Any]], devices: list[dict[str, Any]]
) -> None:
    """요구사항이 충족될 때까지만 fallback spec 을 추가한다.

    예전에는 fallback 리스트 전체를 append 해서 LLM 이 이미 만든 항목 위에 4장이 더
    붙어 하루 8장까지 불어났다. 이제는 schedule_task / automation_rule 누락분과
    MIN_TOTAL_ITEMS 부족분만 채운다(EXACT_COUNT_SURFACES 는 _top_up_exact_counts 로 위임).
    """
    surface = state["surface"]
    if surface in EXACT_COUNT_SURFACES:
        _top_up_exact_counts(state, items, devices)
        return

    device_id = _pick_device_id(devices, surface)
    for spec in _FALLBACK_ACTIONS[surface]:
        if _meets_requirements(items, surface):
            return
        if spec["actionType"] == "automation_rule" and device_id is None:
            continue

        actionable_types = {item.get("actionType") for item in items if item.get("actionable")}
        needs_type = spec["actionType"] not in actionable_types
        needs_count = len(items) < MIN_TOTAL_ITEMS
        if not needs_type and not needs_count:
            continue
        items.append(_build_actionable_item(state, spec, device_id))


def _top_up_exact_counts(
    state: InsightGenerationState, items: list[dict[str, Any]], devices: list[dict[str, Any]]
) -> None:
    """EXACT_COUNT_SURFACES 전용 top-up — automation_rule 액션/schedule_task 액션/tip 을
    각각 부족한 만큼만 채운다(호출 시점엔 이미 _finalize_exact_counts 로 트림된 뒤라 정확한
    부족분만 남아 있다). 개수뿐 아니라 actionType 도 하나씩 서로 달라야 하므로, 이미 있는
    actionType 은 건너뛰고 없는 쪽만 채운다."""
    surface = state["surface"]
    device_id = _pick_device_id(devices, surface)

    has_rule_action = any(
        item.get("kind") == "action" and item.get("actionable") and item.get("actionType") == "automation_rule"
        for item in items
    )
    has_task_action = any(
        item.get("kind") == "action" and item.get("actionable") and item.get("actionType") == "schedule_task"
        for item in items
    )
    for spec in _FALLBACK_ACTIONS.get(surface, []):
        if has_rule_action and has_task_action:
            break
        if spec["actionType"] == "automation_rule":
            if has_rule_action or device_id is None:
                continue
            items.append(_build_actionable_item(state, spec, device_id))
            has_rule_action = True
        else:
            if has_task_action:
                continue
            items.append(_build_actionable_item(state, spec, device_id))
            has_task_action = True

    tip_count = sum(1 for item in items if item.get("kind") == "tip")
    for spec in _FALLBACK_TIPS.get(surface, []):
        if tip_count >= EXACT_TIP_COUNT:
            break
        items.append(_build_tip_item(state, spec))
        tip_count += 1


async def _fetch_devices(user_id: int) -> list[dict[str, Any]]:
    """automation_rule 검증·폴백에 항상 필요해서, LLM 의 tool 선택에 맡기지 않고 gather
    단계에서 결정적으로 조회한다(LLM 에게 맡겼을 때는 3번 중 1번만 device 를 조회했다).

    1) device_user_map 이 채워져 있으면 device?filter=userId 단일 쿼리로 끝난다 - 왕복이
       1회뿐이고, room 단위가 아니라 장치 단위 권한이라 더 정확하다(같은 방을 공유해도
       특정 장치만 비공개로 둘 수 있음).
    2) 이 real backend 는 현재 device_user_map 이 비어 있어(room_user_map 만 시딩됨) 1)이
       매번 0건이라, room_user_map -> device(roomId) 경유(devices_internal.py 의
       list_devices/resolve_device_id 와 동일한 방식)로 대체한다."""
    [direct] = await query_db([DbQuery(table="device", filter={"userId": user_id, "archived": 0})])
    if direct.error is None and direct.items:
        return direct.items

    [room_result] = await query_db([DbQuery(table="room_user_map", filter={"userId": user_id})])
    if room_result.error is not None:
        return []
    room_ids = [row["roomId"] for row in room_result.items]
    if not room_ids:
        return []

    devices: list[dict[str, Any]] = []
    seen_ids: set[Any] = set()
    for room_id in room_ids:
        [result] = await query_db([DbQuery(table="device", filter={"roomId": room_id, "archived": 0})])
        if result.error is not None:
            continue
        for item in result.items:
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                devices.append(item)
    return devices


async def _fetch_action_names_by_class() -> dict[str, set[str]]:
    """automation_rule 의 action.name 검증·프롬프트 grounding 에 쓸, 클래스별 실제 action
    이름 집합을 device 목록과 마찬가지로 LLM 의 tool 선택에 맡기지 않고 결정적으로
    조회한다. GET /internal/v1/device-classes 는 devicesReady() 게이트가 없는 정적
    레지스트리라 --no-devices 에서도 항상 응답한다(devices_internal.get_device_classes()
    가 mock/real 을 알아서 분기)."""
    try:
        classes = await devices_internal.get_device_classes()
    except InternalApiError:
        return {}
    return {c.class_: {action.name for action in c.actions} for c in classes}


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
        system_prompt_fn=lambda _state: _context_system_prompt(surface),
    )
    result = await loop.ainvoke({"messages": [_seed_message(state)], "rounds": 0})
    devices = await _fetch_devices(state["user_id"])
    action_names_by_class = await _fetch_action_names_by_class()
    return {"messages": result["messages"], "devices": devices, "action_names_by_class": action_names_by_class}


def _needs_actionable(state: InsightGenerationState) -> bool:
    return state["surface"] in REQUIRE_ACTIONABLE_SURFACES or state["surface"] in EXACT_COUNT_SURFACES


def _actionable_requirement_text(surface: str) -> str:
    if surface in EXACT_COUNT_SURFACES:
        return _EXACT_COUNT_REQUIREMENT_TEXT
    if surface in REQUIRE_ACTIONABLE_SURFACES:
        return _ACTIONABLE_REQUIREMENT_TEXT
    return ""


def _retry_feedback_text(surface: str) -> str:
    return _EXACT_COUNT_RETRY_FEEDBACK_TEXT if surface in EXACT_COUNT_SURFACES else _RETRY_FEEDBACK_TEXT


async def generate(state: InsightGenerationState) -> dict[str, Any]:
    attempt = state.get("generate_attempts", 0)  # 이 호출이 몇 번째 시도인지(0-based)
    extra_context = _extract_tool_results(state.get("messages", []))
    devices = state.get("devices", [])
    action_names_by_class = state.get("action_names_by_class", {})
    surface = state["surface"]
    prompt = load_prompt(
        "insight",
        "generate",
        user_id=state["user_id"],
        surface=surface,
        date=state["date"],
        context=json.dumps(state.get("context") or {}, ensure_ascii=False),
        extra_context=json.dumps(extra_context, ensure_ascii=False),
        devices=json.dumps(_devices_with_actions(devices, action_names_by_class), ensure_ascii=False),
        retry_feedback=_retry_feedback_text(surface) if attempt > 0 else "",
        actionable_requirement=_actionable_requirement_text(surface),
        length_guidance=_length_guidance(surface),
        actionable_guidance=_actionable_guidance(surface),
        item_count_guidance=_item_count_guidance(surface),
    )
    batch = await invoke_structured(GeneratedInsightBatch, prompt, fallback=GeneratedInsightBatch(items=[]))
    items = [item.model_dump() for item in batch.items]
    if surface in _NARRATIVE_ONLY_SURFACES:
        items = _force_narrative_only(items)
    else:
        items = _validate_automation_rules(items, devices, action_names_by_class)
        # EXACT_COUNT_SURFACES(sleep_report/power)만 여기서 실질적으로 자른다 - 검증
        # (강등)이 먼저 끝난 뒤에 트림해야, 무효화된 automation_rule 이 action 슬롯을
        # 차지한 채로 살아남지 않는다. 다른 surface 에는 영향 없음(그대로 반환).
        items = _finalize_exact_counts(items, surface)
    attempts_done = attempt + 1

    if _needs_actionable(state) and not _meets_requirements(items, surface) and attempts_done >= MAX_GENERATE_ATTEMPTS:
        # 재시도 예산 소진 — 규칙 기반 fallback 으로 계약(REQUIRE_ACTIONABLE_SURFACES 는
        # "schedule_task/automation_rule 각 1개 이상", EXACT_COUNT_SURFACES 는 "action/tip
        # 정확히 N개")을 강제한다.
        _top_up_items(state, items, devices)
        # top-up 이 만든 항목도 동일 기준으로 재검증한다(현재 폴백은 항상 "off" 를 쓰는데,
        # 이는 우연이 아니라 _PREFERRED_DEVICE_CLASSES 의 클래스들이 전부 "off" 를 갖고
        # 있어서다 - 앞으로 선호 클래스가 바뀌어도 이 가드가 잡아준다).
        items = _validate_automation_rules(items, devices, action_names_by_class)
        items = _finalize_exact_counts(items, surface)  # 안전망 재트림(정상 경로에선 no-op)

    # 검증·top-up 은 내부 규약(int)으로 끝내고, 응답으로 내보내기 직전 마지막 단계에서만
    # wire 포맷(hex)으로 바꾼다 - _validate_automation_rules 의 valid_ids 비교가 int 매칭에
    # 의존하므로 순서를 바꾸면 안 된다.
    items = _rulejson_device_ids_to_wire(items, devices)

    return {"items": items, "generate_attempts": attempts_done}


def _meets_requirements(items: list[dict[str, Any]], surface: str) -> bool:
    if surface in EXACT_COUNT_SURFACES:
        action_types = [
            item.get("actionType") for item in items if item.get("kind") == "action" and item.get("actionable")
        ]
        tips = [item for item in items if item.get("kind") == "tip"]
        return sorted(action_types) == ["automation_rule", "schedule_task"] and len(tips) == EXACT_TIP_COUNT
    actionable_types = {item["actionType"] for item in items if item["actionable"]}
    return "schedule_task" in actionable_types and "automation_rule" in actionable_types and len(items) >= MIN_TOTAL_ITEMS


def _should_retry_generate(state: InsightGenerationState) -> str:
    if not _needs_actionable(state):
        return END
    if _meets_requirements(state.get("items", []), state["surface"]):
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
