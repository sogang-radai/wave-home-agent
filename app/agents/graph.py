import warnings
from typing import Any, Optional

warnings.filterwarnings(
    "ignore",
    message="The default value of `allowed_objects` will change.*",
)

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState, AgentTask
from app.clients.core import CoreApiClient


def _classify_intent(message: Optional[str], task: AgentTask) -> str:
    if task != "chat":
        return task

    text = (message or "").lower()
    if any(keyword in text for keyword in ["불", "조명", "에어컨", "온도", "소등"]):
        return "device_control"
    if any(keyword in text for keyword in ["일정", "운동", "내일", "옮겨"]):
        return "schedule_management"
    if any(keyword in text for keyword in ["수면", "잠", "어젯밤"]):
        return "sleep_consultation"
    if any(keyword in text for keyword in ["자세", "허리", "목"]):
        return "posture_consultation"
    return "general_health_chat"


async def classify(state: AgentState) -> AgentState:
    return {"intent": _classify_intent(state.get("user_message"), state["task"])}


async def fetch_context(state: AgentState) -> AgentState:
    client = CoreApiClient()
    context = await client.get_context(
        account_id=state["account_id"],
        task=state["task"],
        user_message=state.get("user_message"),
        metadata=state.get("metadata", {}),
    )
    return {"context": context, "sources": ["core-api"]}


async def generate(state: AgentState) -> AgentState:
    task = state["task"]
    intent = state.get("intent", task)
    context = state.get("context", {})

    if task == "chat":
        return _generate_chat_response(intent=intent, context=context)
    if task == "recommend_actions":
        return _generate_action_recommendations()
    return _generate_report(task=task)


def _generate_chat_response(*, intent: str, context: dict[str, Any]) -> AgentState:
    actions: list[dict[str, Any]] = []

    if intent == "device_control":
        actions.append(
            {
                "type": "device_control_request",
                "status": "planned",
                "description": "C++ 서버의 기기 제어 API로 전달할 액션입니다.",
            }
        )
        answer = "요청하신 가전 제어 의도를 확인했습니다. 실제 실행은 C++ 서버 API를 통해 처리하도록 준비하겠습니다."
    elif intent == "schedule_management":
        actions.append(
            {
                "type": "schedule_update_request",
                "status": "planned",
                "description": "C++ 서버의 일정 API로 전달할 액션입니다.",
            }
        )
        answer = "일정 변경 요청으로 이해했습니다. 변경 대상 일정을 확인한 뒤 C++ 서버 API로 요청하는 흐름을 연결하면 됩니다."
    elif intent == "sleep_consultation":
        sleep = context.get("sleep", {})
        last_night = sleep.get("lastNight", {})
        answer = (
            "어젯밤 수면은 보통 수준으로 보입니다. "
            f"총 수면 시간은 약 {last_night.get('durationMinutes', 'N/A')}분이고, "
            f"중간 각성은 {last_night.get('wakeUps', 'N/A')}회로 기록되어 있습니다."
        )
    elif intent == "posture_consultation":
        posture = context.get("posture", {}).get("today", {})
        answer = (
            "오늘 자세 데이터 기준으로 장시간 나쁜 자세가 누적되는 구간이 있습니다. "
            f"좋은 자세 비율은 약 {posture.get('goodPostureRatio', 0) * 100:.0f}%입니다."
        )
    else:
        answer = "현재 수면, 자세, 일정, 기기 상태 데이터를 바탕으로 건강 상담과 생활 인사이트를 제공할 수 있습니다."

    return {
        "answer": answer,
        "actions": actions,
        "sources": ["core-api"],
    }


def _generate_report(*, task: AgentTask) -> AgentState:
    titles = {
        "weekly_sleep_report": "이번 주 수면 리포트",
        "nightly_sleep_report": "어젯밤 수면 리포트",
        "weekly_posture_report": "이번 주 자세 리포트",
        "daily_posture_report": "오늘의 자세 리포트",
    }

    return {
        "title": titles[task],
        "summary": "C++ 서버에서 받은 수면/자세 컨텍스트를 기반으로 생성한 기본 리포트입니다.",
        "highlights": [
            "최근 데이터의 주요 변화 지점을 요약합니다.",
            "위험 신호가 있으면 우선순위를 높여 표시합니다.",
        ],
        "recommendations": [
            "취침 전 조명과 실내 온도를 일정하게 유지하세요.",
            "장시간 앉아 있는 구간에는 짧은 스트레칭을 추가하세요.",
        ],
        "sources": ["core-api"],
    }


def _generate_action_recommendations() -> AgentState:
    return {
        "summary": "수면과 자세 데이터를 바탕으로 오늘 실행하기 좋은 액션을 추천합니다.",
        "recommendations": [
            "잠들기 30분 전 조명을 낮추기",
            "나쁜 자세가 길어진 뒤 3분 스트레칭하기",
        ],
        "actions": [
            {
                "type": "automation_suggestion",
                "description": "취침 시간에 맞춰 조명 밝기를 낮추는 자동화를 제안합니다.",
            }
        ],
        "sources": ["core-api"],
    }


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("classify", classify)
    graph.add_node("fetch_context", fetch_context)
    graph.add_node("generate", generate)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "fetch_context")
    graph.add_edge("fetch_context", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


agent_graph = build_graph()


async def run_agent(
    *,
    task: AgentTask,
    account_id: str,
    user_message: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    initial_state: AgentState = {
        "task": task,
        "account_id": account_id,
        "user_message": user_message,
        "metadata": metadata or {},
    }
    result = await agent_graph.ainvoke(initial_state)
    return {"task": task, "intent": result.get("intent", task), **result}
