"""Shared 2-node ReAct tool-calling loop, reused by the chat turn graph and the
report graph's optional context-gathering phase.

langgraph>=1.0 dropped langgraph.prebuilt.ToolNode/create_react_agent (moved
into the `langchain` package's agent APIs), so tool execution here is a small
custom node instead of relying on that prebuilt. This also keeps the node
body simple enough to attach LangChain tracing (on_tool_start/on_tool_end/
on_tool_error events, which app/graph/chat_runtime.py listens for) without
fighting an external abstraction.
"""

import logging
from typing import Any, Callable

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.services.llm import get_llm


logger = logging.getLogger(__name__)

NO_LLM_FALLBACK_TEXT = "현재 AI 모델을 사용할 수 없어 제한된 답변만 제공할 수 있습니다."


def _preview(value: Any, limit: int = 500) -> str:
    """Renders a tool arg/result for a single-line log entry, capped so a
    large tool result (e.g. a device or rule list) doesn't blow up the log."""
    text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}...(truncated)"


def build_tool_loop(
    state_schema: type,
    tools: list[BaseTool],
    *,
    max_rounds: int,
    system_prompt_fn: Callable[[dict[str, Any]], str],
) -> CompiledStateGraph:
    tool_by_name = {t.name: t for t in tools}

    async def agent_node(state: dict[str, Any]) -> dict[str, Any]:
        llm = get_llm(state.get("model"))
        rounds = state.get("rounds", 0)
        if llm is None:
            return {"messages": [AIMessage(content=NO_LLM_FALLBACK_TEXT)], "rounds": rounds + 1}

        # Once the round budget is spent, drop tool binding so the model is
        # forced to produce a final text answer instead of requesting yet
        # another tool call that would otherwise dead-end the loop.
        bound = llm.bind_tools(tools) if rounds < max_rounds else llm
        system = SystemMessage(content=system_prompt_fn(state))
        response = await bound.ainvoke([system, *state["messages"]])
        return {"messages": [response], "rounds": rounds + 1}

    async def tool_node(state: dict[str, Any]) -> dict[str, Any]:
        last = state["messages"][-1]
        results: list[ToolMessage] = []
        for call in last.tool_calls:
            tool_fn = tool_by_name.get(call["name"])
            if tool_fn is None:
                logger.warning("tool call: name=%s args=%s -> unknown tool", call["name"], call["args"])
                results.append(
                    ToolMessage(content=f"알 수 없는 tool입니다: {call['name']}", tool_call_id=call["id"], status="error")
                )
                continue
            logger.info("tool call: name=%s args=%s", call["name"], call["args"])
            try:
                content = await tool_fn.ainvoke(call["args"])
                logger.info("tool call ok: name=%s result=%s", call["name"], _preview(content))
                results.append(
                    ToolMessage(content=str(content), tool_call_id=call["id"], name=call["name"], status="success")
                )
            except Exception as exc:  # tool errors must not crash the turn (api.md §2.1)
                logger.warning("tool call failed: name=%s args=%s error=%s", call["name"], call["args"], exc)
                results.append(
                    ToolMessage(content=str(exc), tool_call_id=call["id"], name=call["name"], status="error")
                )
        return {"messages": results}

    def should_continue(state: dict[str, Any]) -> str:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None) and state.get("rounds", 0) < max_rounds:
            return "tools"
        return END

    graph = StateGraph(state_schema)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    # Explicit path_map (not just the bare function) so draw_mermaid() can
    # enumerate both branches instead of collapsing to a single edge to END.
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()
