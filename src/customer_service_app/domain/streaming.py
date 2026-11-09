"""Public SSE contract. No graph state, tool arguments, prompts or exception strings."""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from uuid import uuid4


class PublicPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartedPayload(PublicPayload):
    status: str = "running"


class NodePayload(PublicPayload):
    node: str


class PublicKnowledge(PublicPayload):
    id: str
    source: str
    title: str
    content: str


class KnowledgePayload(PublicPayload):
    knowledge: list[PublicKnowledge]


class ToolPayload(PublicPayload):
    tool: str
    call_id: str
    execution_status: str | None = None
    business_status: str | None = None


class DeltaPayload(PublicPayload):
    text: str


class PublicConfirmation(PublicPayload):
    id: str
    action_type: str
    tool_name: str
    status: str
    order_id: str | None = None
    reason: str | None = None


class ConfirmationPayload(PublicPayload):
    confirmation: PublicConfirmation


class CompletedPayload(PublicPayload):
    status: str
    answer: str
    persisted: bool = True


class FailurePayload(PublicPayload):
    code: str
    message: str
    status: Literal["failed", "unknown"] = "failed"


class HeartbeatPayload(PublicPayload):
    pass


PAYLOAD_TYPES = {
    "run_started": StartedPayload, "node_completed": NodePayload,
    "knowledge_ready": KnowledgePayload, "tool_started": ToolPayload,
    "tool_completed": ToolPayload, "answer_delta": DeltaPayload,
    "confirmation_required": ConfirmationPayload, "run_completed": CompletedPayload,
    "run_failed": FailurePayload, "stream_interrupted": FailurePayload, "heartbeat": HeartbeatPayload,
}


class StreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    event_type: Literal["run_started", "node_completed", "knowledge_ready", "tool_started",
                        "tool_completed", "answer_delta", "confirmation_required", "run_completed",
                        "run_failed", "stream_interrupted", "heartbeat"]
    run_id: str | None
    conversation_id: str | None
    thread_id: str | None
    sequence: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: StartedPayload | NodePayload | KnowledgePayload | ToolPayload | DeltaPayload | ConfirmationPayload | CompletedPayload | FailurePayload | HeartbeatPayload

    @model_validator(mode="before")
    @classmethod
    def validate_payload(cls, data):
        if isinstance(data, dict) and data.get("event_type") in PAYLOAD_TYPES:
            data = dict(data)
            data["payload"] = PAYLOAD_TYPES[data["event_type"]].model_validate(data.get("payload", {}))
        return data

    def sse(self) -> str:
        return f"id: {self.event_id}\nevent: {self.event_type}\ndata: {self.model_dump_json()}\n\n"


class EventFactory:
    def __init__(self, conversation_id: str | None = None, thread_id: str | None = None):
        self.stream_id = str(uuid4())
        self.run_id: str | None = None
        self.conversation_id = conversation_id
        self.thread_id = thread_id
        self.sequence = 0

    def make(self, event_type: str, payload: dict) -> StreamEvent:
        self.sequence += 1
        return StreamEvent(event_id=f"{self.stream_id}:{self.sequence}", event_type=event_type,
            run_id=self.run_id, conversation_id=self.conversation_id, thread_id=self.thread_id,
            sequence=self.sequence, payload=payload)
