import json
from typing import Any, AsyncIterator, Callable, Awaitable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.config import get_settings
from app.graph.tools import build_tools
from app.graph.turn_graph import build_chat_graph, scrub_disclaimer
from app.schemas.chat import ChatTurnRequest, ChatTurnResponse, ToolCallRecord
from app.state.chat_state import ChatTurnState


_ROLE_TO_MESSAGE = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


def _extract_text(content: Any) -> str:
    """ChatGoogleGenerativeAI streams `.content` as either a plain string or a
    list of content blocks (e.g. [{"type": "text", "text": "..."}]) depending
    on the response shape; normalize to plain text for SSE/JSON output."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""


def _to_initial_state(body: ChatTurnRequest) -> ChatTurnState:
    messages = [_ROLE_TO_MESSAGE[m.role](content=m.content) for m in body.messages]
    return ChatTurnState(
        messages=messages,
        user_id=body.userId,
        chat_history_id=body.chatHistoryId,
        now=body.context.now,
        retrieved=[r.model_dump() for r in body.context.retrieved],
        model=body.model,
        rounds=0,
    )


def _sse(obj: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode()


def _to_error_payload(exc: Exception) -> dict[str, Any]:
    return {"code": "LLM_PROVIDER_ERROR", "message": str(exc)}


def _summarize_tool_result(name: str, raw: str) -> Any:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {"raw": raw[:200]}
    if isinstance(parsed, list):
        # query_db/rag_search return one entry per requested query/target, each
        # itself carrying its own row "count" - sum those instead of reporting
        # how many queries were sent.
        if parsed and all(isinstance(entry, dict) and "count" in entry for entry in parsed):
            return {"count": sum(entry["count"] for entry in parsed)}
        if parsed and all(isinstance(entry, dict) and "hits" in entry for entry in parsed):
            return {"count": sum(len(entry["hits"]) for entry in parsed)}
        return {"count": len(parsed)}
    if isinstance(parsed, dict):
        return parsed
    return {"raw": str(parsed)[:200]}


async def stream_turn(body: ChatTurnRequest, disconnect: Callable[[], Awaitable[bool]]) -> AsyncIterator[bytes]:
    tools = build_tools(body.userId)
    graph = build_chat_graph(tools)
    state = _to_initial_state(body)
    current_answer = ""

    try:
        async for event in graph.astream_events(state, version="v2"):
            if await disconnect():
                break
            kind = event["event"]
            node = event.get("metadata", {}).get("langgraph_node")

            if kind == "on_chat_model_start" and node == "agent":
                current_answer = ""
            elif kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                text = _extract_text(chunk.content)
                if text:
                    current_answer += text
                    yield _sse({"type": "message.delta", "content": text})
            elif kind == "on_tool_start":
                yield _sse({"type": "tool.start", "name": event["name"], "args": event["data"].get("input")})
            elif kind == "on_tool_end":
                output = event["data"].get("output")
                yield _sse(
                    {
                        "type": "tool.end",
                        "name": event["name"],
                        "ok": True,
                        "result": _summarize_tool_result(event["name"], str(output)),
                    }
                )
            elif kind == "on_tool_error":
                error = event["data"].get("error")
                yield _sse({"type": "tool.end", "name": event["name"], "ok": False, "result": str(error)})

        final_answer = scrub_disclaimer(current_answer) if current_answer else current_answer
        yield _sse(
            {
                "type": "message.completed",
                "content": final_answer,
                "model": body.model or get_settings().gemini_model,
            }
        )
        yield b"data: [DONE]\n\n"
    except Exception as exc:  # noqa: BLE001 - narrow on purpose: GeneratorExit must propagate for cancellation
        yield _sse({"type": "error", "error": _to_error_payload(exc)})


async def run_turn_sync(body: ChatTurnRequest) -> ChatTurnResponse:
    tools = build_tools(body.userId)
    graph = build_chat_graph(tools)
    state = _to_initial_state(body)

    result = await graph.ainvoke(state)
    messages = result["messages"]

    tool_calls: list[ToolCallRecord] = []
    pending: dict[str, dict[str, Any]] = {}
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                pending[call["id"]] = {"name": call["name"], "args": call["args"]}
        elif isinstance(message, ToolMessage) and message.tool_call_id in pending:
            record = pending.pop(message.tool_call_id)
            tool_calls.append(
                ToolCallRecord(
                    name=record["name"],
                    args=record["args"],
                    ok=message.status != "error",
                    result=_summarize_tool_result(record["name"], str(message.content)),
                )
            )

    last = messages[-1]
    content = scrub_disclaimer(_extract_text(last.content)) if last.content else ""
    return ChatTurnResponse(content=content, model=body.model or get_settings().gemini_model, toolCalls=tool_calls)
