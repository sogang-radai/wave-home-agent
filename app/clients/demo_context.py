from contextvars import ContextVar, Token
from typing import Optional

_demo_runtime_id: ContextVar[Optional[str]] = ContextVar("demo_runtime_id", default=None)


def set_demo_runtime_id(value: Optional[str]) -> Token:
    return _demo_runtime_id.set(value)


def get_demo_runtime_id() -> Optional[str]:
    return _demo_runtime_id.get()


def reset_demo_runtime_id(token: Token) -> None:
    _demo_runtime_id.reset(token)
