"""Process-local execution context; never trusted from request metadata or checkpointed."""
from contextvars import ContextVar
from langgraph.config import get_stream_writer

streaming: ContextVar[bool] = ContextVar("agent_streaming", default=False)


def emit(event_type: str, payload: dict) -> None:
    if streaming.get():
        get_stream_writer()({"event_type": event_type, "payload": payload})
