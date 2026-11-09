from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolOutcome(BaseModel):
    execution_status: Literal["success", "error", "timeout"]
    business_status: Literal["satisfied", "not_satisfied", "unknown"]
    data: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    attempts: int = 1

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> "ToolOutcome":
        if data.get("error"):
            return cls(execution_status="error", business_status="unknown", data=data, error_code="tool_reported_error")
        rejected = any(data.get(key) is False for key in ("found", "allowed", "eligible", "ok"))
        unknown = not rejected and not data
        return cls(execution_status="success", business_status=(
            "not_satisfied" if rejected else "unknown" if unknown else "satisfied"), data=data)
