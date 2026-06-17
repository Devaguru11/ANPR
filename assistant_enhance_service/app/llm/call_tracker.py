from __future__ import annotations
from contextvars import ContextVar
_llm_calls: ContextVar[int] = ContextVar('llm_calls', default=0)

def reset_llm_calls() -> None:
    _llm_calls.set(0)

def record_llm_call() -> None:
    _llm_calls.set(_llm_calls.get() + 1)

def get_llm_calls() -> int:
    return _llm_calls.get()