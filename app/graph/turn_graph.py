from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.graph.chat_subgraphs import build_domain_subgraph
from app.graph.domain_router import DOMAINS, classify_domain
from app.state.chat_state import ChatTurnState


_BANNED_PHRASES = ("진단합니다", "처방", "질병명")


async def _route(state: dict[str, Any]) -> dict[str, Any]:
    domain = await classify_domain(state.get("messages", []))
    return {"domain": domain}


def _select_domain(state: dict[str, Any]) -> str:
    return state.get("domain") or "general"


def build_chat_graph(user_id: int) -> CompiledStateGraph:
    """router -> one domain subgraph -> END. The router classifies the turn
    (app/graph/domain_router.py) and each domain subgraph
    (app/graph/chat_subgraphs.py) runs its own ReAct tool loop scoped to that
    domain's tools, replacing the single general-purpose agent that used to
    hold every tool at once."""
    graph = StateGraph(ChatTurnState)
    graph.add_node("router", _route)
    for domain in DOMAINS:
        graph.add_node(domain, build_domain_subgraph(domain, user_id))
        graph.add_edge(domain, END)
    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _select_domain, {domain: domain for domain in DOMAINS})
    return graph.compile()


def scrub_disclaimer(text: str) -> str:
    """Defense-in-depth: the system prompt already forbids this, but scrub any
    banned phrase that slips through, mirroring the old chat_graph.py's
    validate_response idea."""
    scrubbed = text
    for phrase in _BANNED_PHRASES:
        if phrase in scrubbed:
            scrubbed = scrubbed.replace(phrase, "").strip()
            scrubbed += " (이 답변은 의료적 진단이 아닙니다.)"
            break
    return scrubbed
