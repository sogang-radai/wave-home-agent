"""Traces one /chat/v1/turns turn through app/graph/turn_graph.py node by node:
which domain(s) got classified, which domain nodes ran, and every message
(tool calls, tool results, final answers) each one produced - without going
through the SSE layer.

Usage:
    python scripts/trace_chat_turn.py "이번주 전반적인 건강 어땠어?"
    python scripts/trace_chat_turn.py "어젯밤 몇 시간 잤어?" --user-id 7
"""
import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.graph.turn_graph import build_chat_graph


def _fmt_message(message: Any) -> str:
    if isinstance(message, ToolMessage):
        return f"ToolMessage(name={message.name}, content={str(message.content)[:160]!r})"
    if isinstance(message, AIMessage):
        content = message.content
        text = "".join(b.get("text", "") for b in content if isinstance(b, dict)) if isinstance(content, list) else content
        tool_calls = [c["name"] for c in (message.tool_calls or [])]
        return f"AIMessage(tool_calls={tool_calls}, text={text[:200]!r})"
    return f"{type(message).__name__}({message.content!r})"


async def trace(user_message: str, user_id: int) -> None:
    graph = build_chat_graph(user_id)
    state = {
        "messages": [HumanMessage(content=user_message)],
        "user_id": user_id,
        "chat_history_id": 1,
        "now": None,
        "retrieved": [],
        "model": None,
        "rounds": 0,
    }

    step = 0
    async for update in graph.astream(state, stream_mode="updates"):
        step += 1
        for node_name, node_output in update.items():
            print(f'--- step {step}: node="{node_name}" ---')
            # A node that returns {} (e.g. synthesize's single-domain no-op
            # passthrough - app/graph/turn_graph.py) surfaces here as None,
            # not {}.
            node_output = node_output or {}
            if "domains" in node_output:
                print(f"  domains(분류 결과) = {node_output['domains']}")
            for answer in node_output.get("domain_answers", []):
                print(f"  domain_answers += domain={answer['domain']!r}, text={answer['text'][:120]!r}")
            for message in node_output.get("messages", []):
                print(f"  messages += {_fmt_message(message)}")
            print()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("message", help="사용자 메시지")
    parser.add_argument("--user-id", type=int, default=42)
    args = parser.parse_args()

    asyncio.run(trace(args.message, args.user_id))


if __name__ == "__main__":
    main()
