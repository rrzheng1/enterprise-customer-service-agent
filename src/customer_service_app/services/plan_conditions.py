from __future__ import annotations

from typing import Any

from customer_service_app.domain.planning import PlanStep
from customer_service_app.domain.tool_outcome import ToolOutcome

MISSING = object()


def outcomes_by_step(observations: list[dict]) -> dict[str, dict]:
    return {item["step_id"]: item.get("outcome") or ToolOutcome.from_payload(
        item.get("payload", item.get("result", {}))).model_dump() for item in observations if "step_id" in item}


def read_path(value: dict, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return MISSING
        value = value[key]
    return value


def prepare_step(step: PlanStep, observations: list[dict]) -> tuple[bool, dict, str]:
    outcomes = outcomes_by_step(observations)
    for condition in step.conditions:
        value = read_path(outcomes.get(condition.step_id, {}), condition.path)
        matched = False
        if condition.operator == "exists":
            matched = value is not MISSING
        elif value is not MISSING:
            if condition.operator == "eq":
                matched = type(value) is type(condition.value) and value == condition.value
            elif condition.operator == "ne":
                matched = type(value) is type(condition.value) and value != condition.value
            elif condition.operator == "in" and isinstance(condition.value, list):
                matched = any(type(value) is type(item) and value == item for item in condition.value)
        if not matched:
            return False, {}, "condition_not_met"
    arguments = dict(step.arguments)
    for name, reference in step.argument_refs.items():
        value = read_path(outcomes.get(reference.step_id, {}), reference.path)
        if value is MISSING:
            return False, {}, "missing_output_reference"
        arguments[name] = value
    return True, arguments, "ready"
