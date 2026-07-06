import json
from typing import Any

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from app.graph import health_graph
from app.services.llm import invoke_structured
from app.services.prompts import load_prompt
from app.state.agent_state import AgentState


_SLEEP_KEYWORDS = ["수면", "잠", "어젯밤"]
_POSTURE_KEYWORDS = ["자세", "허리", "목"]
_GENERAL_HEALTH_KEYWORDS = ["건강", "컨디션", "요즘 어때"]
_BANNED_PHRASES = ["진단합니다", "처방", "질병명"]
_DOMAIN_LABELS = {"sleep": "수면", "posture": "자세", "observation": "생활 패턴", "lifestyle": "생활 습관"}
_DOMAIN_TEXT_KEYWORDS = {
    "sleep": _SLEEP_KEYWORDS,
    "posture": _POSTURE_KEYWORDS,
    "observation": ["카메라", "활동량", "야간 행동"],
    "lifestyle": ["운동 습관", "생활 습관"],
}

_FALLBACK_ANSWER = "현재 수면, 자세, 일정, 기기 상태 데이터를 바탕으로 건강 상담과 생활 인사이트를 제공할 수 있습니다."


class ChatAnswer(BaseModel):
    answer: str


async def normalize_request(state: AgentState) -> dict[str, Any]:
    request = dict(state.get("request", {}))
    request["message"] = (request.get("message") or "").strip()
    return {"request": request}


async def need_context(state: AgentState) -> dict[str, Any]:
    message = state["request"].get("message", "")
    if any(k in message for k in _SLEEP_KEYWORDS):
        return {"required_context": ["sleep"], "intent": "sleep_consultation"}
    if any(k in message for k in _POSTURE_KEYWORDS):
        return {"required_context": ["posture"], "intent": "posture_consultation"}
    if any(k in message for k in _GENERAL_HEALTH_KEYWORDS):
        return {"required_context": ["sleep", "posture", "observation", "lifestyle"], "intent": "general_health_chat"}
    return {"required_context": [], "intent": "general_chat"}


def route_need_context(state: AgentState) -> str:
    return "health_analysis" if state.get("required_context") else "generate_response"


async def generate_response(state: AgentState) -> dict[str, Any]:
    health = state.get("health_insights")
    if not health:
        return {"response": _FALLBACK_ANSWER}

    fallback = ChatAnswer(answer=health.get("summary", _FALLBACK_ANSWER))
    prompt = load_prompt(
        "system",
        "chat_response",
        question=state["request"].get("message", ""),
        health_summary=json.dumps(health, ensure_ascii=False),
        context="",
    )
    answer = await invoke_structured(ChatAnswer, prompt, fallback=fallback)
    return {"response": answer.answer}


async def validate_response(state: AgentState) -> dict[str, Any]:
    response = state.get("response", "")
    if not response:
        return {"response": _FALLBACK_ANSWER}

    for phrase in _BANNED_PHRASES:
        if phrase in response:
            response = response.replace(phrase, "").strip()
            response += " (이 답변은 의료적 진단이 아닙니다.)"
            break

    health = state.get("health_insights") or {}
    computed_domains = {insight["domain"] for insight in health.get("domains", [])}
    mentioned_in_text = {
        domain for domain, keywords in _DOMAIN_TEXT_KEYWORDS.items() if any(k in response for k in keywords)
    }
    leaked = mentioned_in_text - computed_domains
    if leaked:
        labels = ", ".join(_DOMAIN_LABELS.get(d, d) for d in leaked)
        response += f" ({labels} 관련 언급은 실제 조회한 데이터 기반이 아닐 수 있습니다.)"

    if any(insight.get("confidence") == 0.0 for insight in health.get("domains", [])):
        response += " 일부 데이터를 가져오지 못해 제한된 답변일 수 있습니다."

    return {"response": response}


def build():
    graph = StateGraph(AgentState)
    graph.add_node("normalize_request", normalize_request)
    graph.add_node("need_context", need_context)
    graph.add_node("health_analysis", health_graph.build())
    graph.add_node("generate_response", generate_response)
    graph.add_node("validate_response", validate_response)

    graph.set_entry_point("normalize_request")
    graph.add_edge("normalize_request", "need_context")
    # Explicit path_map so draw_mermaid() can resolve both branches instead of
    # leaving health_analysis/generate_response disconnected in the diagram.
    graph.add_conditional_edges(
        "need_context",
        route_need_context,
        {"health_analysis": "health_analysis", "generate_response": "generate_response"},
    )
    graph.add_edge("health_analysis", "generate_response")
    graph.add_edge("generate_response", "validate_response")
    graph.add_edge("validate_response", END)
    return graph.compile()
