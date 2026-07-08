from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Send

from app.graph.chat_subgraphs import build_domain_subgraph
from app.graph.domain_router import DOMAINS, Domain, classify_domains
from app.services.llm import invoke_text
from app.state.chat_state import ChatTurnState


_BANNED_PHRASES = ("진단합니다", "처방", "질병명")

# Tag applied to a domain node's nested LLM call only when 2+ domains run in
# the same turn (they execute concurrently in the same superstep - LangGraph's
# Send fan-out). app/graph/chat_runtime.py filters chat-model stream events
# carrying this tag out of the SSE answer stream - without it, two domain
# nodes streaming tokens at the same time would interleave into a single
# garbled "current answer" buffer (both use a nested node literally named
# "agent").
BACKGROUND_TAG = "domain_gather"

_SYNTHESIZE_PROMPT = """사용자 질문: {question}

아래는 여러 도메인 담당자가 각자 조사해 답한 내용입니다. 중복되는 내용은 정리하고, 하나의 자연스러운
한국어 답변으로 합쳐서 답하세요. 어떤 도메인이 답했는지는 언급하지 마세요.

{answers}"""


def _extract_text(message: Any) -> str:
    if not isinstance(message, AIMessage):
        return ""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content if isinstance(block, dict))
    return ""


def _last_user_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def gather(state: dict[str, Any]) -> dict[str, Any]:
    """Classifies the turn into 1+ domains. The actual fan-out to each
    domain's node happens via the Send objects returned by _route_to_domains,
    not here - this node only decides which domains are relevant.

    The classification call is always tagged BACKGROUND_TAG - it never
    produces the turn's visible answer, so chat_runtime.py's SSE filter must
    never treat its tokens as the answer stream regardless of domain count."""
    domains = await classify_domains(state.get("messages", []), config={"tags": [BACKGROUND_TAG]})
    return {"domains": domains}


def _route_to_domains(state: dict[str, Any]) -> list[Send]:
    """Turns state["domains"] into one Send per domain, so LangGraph runs each
    domain node in the same superstep (concurrently) - this is what makes the
    fan-out show up as real edges in the compiled graph's diagram instead of
    being hidden inside a single node's function body."""
    domains = state.get("domains") or ["general"]
    return [Send(domain, state) for domain in domains]


def _make_domain_node(domain: Domain, user_id: int):
    """Builds the node function registered for one domain. It wraps that
    domain's ReAct subgraph (app/graph/chat_subgraphs.py) - the subgraph
    itself isn't registered directly as the node because this wrapper also
    needs to (a) tag the nested LLM call as background when 2+ domains are
    running this turn, and (b) shape the result into domain_answers for
    `synthesize`."""

    async def _node(state: dict[str, Any]) -> dict[str, Any]:
        tagged = len(state.get("domains") or []) > 1
        subgraph = build_domain_subgraph(domain, user_id)
        local_state = {
            "messages": state["messages"],
            "user_id": state["user_id"],
            "chat_history_id": state.get("chat_history_id"),
            "now": state.get("now"),
            "retrieved": state.get("retrieved") or [],
            "model": state.get("model"),
            "rounds": 0,
        }
        initial_len = len(local_state["messages"])
        config = {"tags": [BACKGROUND_TAG]} if tagged else {}
        result = await subgraph.ainvoke(local_state, config=config)
        # Only this domain's own new messages, not the shared history it was
        # seeded with (add_messages would dedup that by id anyway, but
        # returning just the delta makes the intent explicit instead of
        # relying on id-dedup across concurrently-running domain nodes).
        new_messages = result["messages"][initial_len:]
        text = _extract_text(new_messages[-1]) if new_messages else ""
        return {"messages": new_messages, "domain_answers": [{"domain": domain, "text": text}]}

    return _node


async def synthesize(state: dict[str, Any]) -> dict[str, Any]:
    """No-op passthrough for the common single-domain case (that domain's own
    final answer, already streamed live, stays as the last message). Runs one
    extra LLM call to merge answers only when 2+ domains actually ran."""
    answers = state.get("domain_answers") or []
    if len(answers) <= 1:
        return {}

    question = _last_user_text(state.get("messages", []))
    joined = "\n\n".join(f"[{a['domain']}]\n{a['text']}" for a in answers)
    fallback = "\n\n".join(a["text"] for a in answers if a["text"])
    text, _ = await invoke_text(
        _SYNTHESIZE_PROMPT.format(question=question, answers=joined),
        fallback=fallback,
        model=state.get("model"),
    )
    return {"messages": [AIMessage(content=text)]}


def build_chat_graph(user_id: int) -> CompiledStateGraph:
    """gather -> {one node per classified domain, run concurrently via Send}
    -> synthesize -> END.

    Each domain node is a real registered node (app/graph/domain_router.py's
    DOMAINS), so the fan-out is visible in the compiled graph's own diagram -
    unlike the earlier version, which ran domain subgraphs from inside a
    single node's Python body via asyncio.gather.
    """
    graph = StateGraph(ChatTurnState)
    graph.add_node("gather", gather)
    graph.add_node("synthesize", synthesize)
    for domain in DOMAINS:
        graph.add_node(domain, _make_domain_node(domain, user_id))
        graph.add_edge(domain, "synthesize")
    graph.set_entry_point("gather")
    graph.add_conditional_edges("gather", _route_to_domains, {domain: domain for domain in DOMAINS})
    graph.add_edge("synthesize", END)
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
