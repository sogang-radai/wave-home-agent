"""Per-domain ReAct subgraphs. Same 2-node tool loop as before
(app/graph/tool_loop.py), but each domain gets only its own tools
(app/graph/domain_tools.py) and a system prompt naming just those tools,
instead of one agent holding every tool every turn.
"""

from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.graph.domain_router import Domain
from app.graph.domain_tools import build_domain_tools
from app.graph.tool_loop import build_tool_loop
from app.state.chat_state import ChatTurnState


MAX_CHAT_ROUNDS = 6

_DOMAIN_INTRO: dict[Domain, str] = {
    "sleep": (
        "당신은 WaveHome의 수면 담당 어시스턴트입니다. 수면 세션/통계/리포트만 다룹니다.\n"
        "사용 가능한 tool: query_db(sleep_session, sleep_stat, sleep_report), "
        "rag_search(sleep_report, sleep_stat)"
    ),
    "power": (
        "당신은 WaveHome의 전력 담당 어시스턴트입니다. 기기 전력/에너지 사용량만 다룹니다.\n"
        "사용 가능한 tool: query_db(power_energy, power_report), rag_search(power_report)"
    ),
    "posture": (
        "당신은 WaveHome의 자세 담당 어시스턴트입니다. 자세/제스처 로그만 다룹니다.\n"
        "사용 가능한 tool: query_db(gesture_set, gesture_log)"
    ),
    "iot": (
        "당신은 WaveHome의 기기/일정/알람 담당 어시스턴트입니다. 기기 조회·제어·예약, "
        "주간/1회 일정, 알람 설정, 카메라 조작만 다룹니다.\n"
        "사용 가능한 tool: list_devices/get_device_capabilities(조회), "
        "control_device/query_device/get_device_state(제어·상태), "
        "get_ptz_capabilities/ptz_move/ptz_stop/ptz_zoom(카메라 팬틸트줌, reolink_e1_pro 전용), "
        "get_camera_stream/set_camera_stream(카메라 실시간 스트림 시작·중지), "
        "send_camera_tts(카메라 스피커로 음성 안내 방송), "
        "schedule_device_action/list_schedules/cancel_schedule(예약), "
        "get_schedule_tasks/create_schedule_task/update_schedule_task/delete_schedule_task(일정), "
        "get_alarms/create_alarm/update_alarm/delete_alarm(알람), "
        "query_db(schedule_task/device/automation_rule/alarm/room/room_user_map만 조회 가능). "
        "장치는 이름(부분일치)+roomId 로 지정하세요, deviceId 를 직접 요구하지 마세요. "
        "'내 방'처럼 사용자가 방을 특정하지 않으면, query_db(room_user_map, filter:{userId}) 또는 "
        "query_db(room, filter:{userId})로 사용자가 속한 방을 먼저 확인한 뒤 그 roomId를 쓰세요. "
        "그래도 방이 여러 개면 사용자에게 되물으세요."
    ),
    "general": (
        "당신은 WaveHome의 건강 및 생활 어시스턴트입니다.\n"
        "사용 가능한 tool: query_db, rag_search, 기기 조회/제어/예약 tool 일체, "
        "일정(schedule_task) CRUD tool 일체, 알람(alarm) CRUD tool 일체"
    ),
}

_COMMON_RULES = """
query_db와 rag_search 사용 구분:
- "어젯밤", "오늘", "정확히 몇 점/몇 분" 처럼 정확한 최신 값이 필요하면 query_db를 먼저 쓰세요.
- "요즘", "최근", "패턴", "이전보다", "왜 그런지" 처럼 장기 맥락·비교·원인 설명이 필요하면 rag_search를
  먼저 써서 과거 리포트/패턴 요약을 찾고, 구체적 수치 확인이 필요하면 query_db로 보완하세요.
- 일정 변경이나 기기 제어처럼 정확한 현재 상태와 실행이 중요한 요청에는 rag_search를 쓰지 마세요.

규칙:
- 반드시 tool 호출로 얻은 사실에 근거해 답변하세요. 조회하지 않은 데이터를 추측해서 말하지 마세요.
- 의학적 진단이나 처방을 내리지 마세요. 필요하면 전문의 상담을 권유하세요.
- 기기 제어나 일정 변경 전에는 무엇을 할 것인지 명확히 파악한 뒤 실행하세요.
- 간결하고 친근한 한국어로 답변하세요.
"""

_RETRIEVED_SECTION_TEMPLATE = """

사전 검색된 참고자료 (필요하면 활용하고, 부족하면 tool로 추가 조회하세요):
{snippets}
"""


def build_domain_system_prompt_fn(domain: Domain):
    def _build(state: dict[str, Any]) -> str:
        prompt = (
            f"{_DOMAIN_INTRO[domain]}\n\n"
            f"현재 시각: {state.get('now') or '알 수 없음'}\n"
            f"{_COMMON_RULES}"
        )
        retrieved = state.get("retrieved") or []
        if retrieved:
            snippets = "\n".join(f"- [{r.get('collection')}] {r.get('text')}" for r in retrieved)
            prompt += _RETRIEVED_SECTION_TEMPLATE.format(snippets=snippets)
        return prompt

    return _build


def build_domain_subgraph(domain: Domain, user_id: int) -> CompiledStateGraph:
    tools = build_domain_tools(domain, user_id)
    return build_tool_loop(
        ChatTurnState,
        tools,
        max_rounds=MAX_CHAT_ROUNDS,
        system_prompt_fn=build_domain_system_prompt_fn(domain),
    )
