"""app/tools/*_internal.py 가 던지는 구조화 에러.

app/graph/tool_loop.py 의 tool_node 가 이미 모든 예외를 잡아
ToolMessage(status="error") 로 바꾸므로(LangGraph tool 호출 규약), 여기서는 절대
app.errors.AgentApiError 로 승격하지 않는다 — 그건 /chat/v1/turns 자체가
400/500 이 되는 것과는 다른 문제다(device-tool-api.md 등 "백엔드가 에이전트에게"
던지는 에러는 챗 턴 안에서 LLM 이 볼 ToolMessage 로만 흘러가야 한다).
"""

from typing import Any, Optional


class InternalApiError(Exception):
    def __init__(self, code: str, message: str, *, detail: Optional[dict[str, Any]] = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.detail = detail
