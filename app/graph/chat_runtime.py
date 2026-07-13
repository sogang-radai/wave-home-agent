import json
from typing import Any, AsyncIterator, Callable, Awaitable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.clients.demo_context import reset_demo_runtime_id, set_demo_runtime_id
from app.graph.turn_graph import BACKGROUND_TAG, build_chat_graph, scrub_disclaimer
from app.schemas.chat import ChatTurnRequest, ChatTurnResponse, ToolCallRecord
from app.services.llm import default_model_name
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


def _tool_run_id(event: dict[str, Any]) -> str:
    run_id = event.get("run_id")
    return str(run_id) if run_id else ""


def _tool_output_ok(output: Any) -> bool:
    """LangGraph ToolNode turns raised tool errors into ToolMessage(status=error)
    and still emits on_tool_end — treat that as ok=false."""
    if isinstance(output, ToolMessage):
        return (output.status or "success") != "error"
    if isinstance(output, list):
        for item in output:
            if isinstance(item, ToolMessage) and (item.status or "success") == "error":
                return False
    return True


def _to_initial_state(body: ChatTurnRequest) -> ChatTurnState:
    personal_parts: list[str] = []
    messages = []
    for message in body.messages:
        content = (message.content or "").strip()
        if not content:
            continue
        if message.role == "system":
            # Replace semantics: wave-server sends the current personal prompt as a
            # single system message. If several arrive, keep only the last so an
            # updated settings prompt never stacks on top of an older one.
            personal_parts.append(content)
            continue
        messages.append(_ROLE_TO_MESSAGE[message.role](content=content))

    return ChatTurnState(
        messages=messages,
        user_id=body.userId,
        chat_history_id=body.chatHistoryId,
        now=body.context.now,
        demo_runtime_id=body.context.demoRuntimeId,
        personal_prompt=personal_parts[-1] if personal_parts else None,
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
    graph = build_chat_graph(body.userId)
    state = _to_initial_state(body)
    demo_token = set_demo_runtime_id(body.context.demoRuntimeId)
    current_answer = ""

    try:
        async for event in graph.astream_events(state, version="v2"):
            if await disconnect():
                break
            kind = event["event"]
            # turn_graph.py tags every chat-model call that is never the
            # turn's visible answer (gather's domain classification always;
            # a domain node's own subgraph only when 2+ domains ran this
            # turn) with BACKGROUND_TAG, so this is the only signal needed -
            # no dependency on any node's literal name.
            background = BACKGROUND_TAG in (event.get("tags") or [])

            if kind == "on_chat_model_start" and not background:
                current_answer = ""
            elif kind == "on_chat_model_stream" and not background:
                chunk = event["data"]["chunk"]
                text = _extract_text(chunk.content)
                if text:
                    current_answer += text
                    yield _sse({"type": "message.delta", "content": text})
            elif kind == "on_tool_start":
                payload = {
                    "type": "tool.start",
                    "name": event["name"],
                    "args": event["data"].get("input"),
                }
                run_id = _tool_run_id(event)
                if run_id:
                    payload["id"] = run_id
                yield _sse(payload)
            elif kind == "on_tool_end":
                output = event["data"].get("output")
                payload = {
                    "type": "tool.end",
                    "name": event["name"],
                    "ok": _tool_output_ok(output),
                    "result": _summarize_tool_result(event["name"], str(output)),
                }
                run_id = _tool_run_id(event)
                if run_id:
                    payload["id"] = run_id
                yield _sse(payload)
            elif kind == "on_tool_error":
                error = event["data"].get("error")
                payload = {
                    "type": "tool.end",
                    "name": event["name"],
                    "ok": False,
                    "result": str(error),
                }
                run_id = _tool_run_id(event)
                if run_id:
                    payload["id"] = run_id
                yield _sse(payload)

        final_answer = scrub_disclaimer(current_answer) if current_answer else current_answer
        yield _sse(
            {
                "type": "message.completed",
                "content": final_answer,
                "model": body.model or default_model_name(),
            }
        )
        yield b"data: [DONE]\n\n"
    except Exception as exc:  # noqa: BLE001 - narrow on purpose: GeneratorExit must propagate for cancellation
        yield _sse({"type": "error", "error": _to_error_payload(exc)})
    finally:
        reset_demo_runtime_id(demo_token)


async def run_turn_sync(body: ChatTurnRequest) -> ChatTurnResponse:
    graph = build_chat_graph(body.userId)
    state = _to_initial_state(body)
    demo_token = set_demo_runtime_id(body.context.demoRuntimeId)

    try:
        result = await graph.ainvoke(state)
    finally:
        reset_demo_runtime_id(demo_token)
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
    return ChatTurnResponse(content=content, model=body.model or default_model_name(), toolCalls=tool_calls)
