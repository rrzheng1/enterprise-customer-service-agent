from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from customer_service_app.core.config import Settings
from customer_service_app.core.exceptions import AppError
from customer_service_app.domain.planning import PlanStep, StepCondition, OutputReference
from customer_service_app.domain.schemas import ChatRequest
from customer_service_app.domain.tool_outcome import ToolOutcome
from customer_service_app.infrastructure.mcp.client import _normalize_tool_result
from customer_service_app.services.plan_conditions import prepare_step
from customer_service_app.services.planner_service import PlannerService
from customer_service_app.services.tool_registry import ToolExecutionContext, ToolRegistry, ToolSpec
from customer_service_app.tools.default_registry import build_default_tool_registry
from customer_service_app.workflows.nodes import CustomerServiceGraphNodes
from customer_service_policy.policy import refund_decision


def eligible_order():
    return {"found": True, "order_id": "202606040003", "status": "delivered", "metadata": {
        "after_sale_review": {"status": "approved", "policy_id": "AFS-DEFECT-015", "policy_version": "1.4",
            "evidence_verified": True, "category_checks_passed": True,
            "approved_refund_types": ["return_refund"],
            "valid_until": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}}}


@pytest.mark.parametrize("facts,reason", [
    ({"found": False}, "order_not_found"),
    ({"found": True, "status": "shipped"}, "requires_further_review"),
    ({"found": True, "status": "delivered", "metadata": {}}, "requires_further_review"),
])
def test_refund_fails_closed_on_missing_facts(facts, reason):
    decision = refund_decision(facts)
    assert not decision["allowed"] and decision["reason"] == reason


def test_expired_or_unverified_review_cannot_be_approved_by_user_text():
    order = eligible_order()
    assert refund_decision(order)["allowed"]
    review = order["metadata"]["after_sale_review"]
    review["evidence_verified"] = "true"
    assert not refund_decision(order)["allowed"]
    review["evidence_verified"] = True
    review["valid_until"] = "2000-01-01T00:00:00Z"
    assert not refund_decision(order)["allowed"]


def test_malformed_business_review_is_not_treated_as_verified_evidence():
    order = eligible_order()
    order["metadata"]["after_sale_review"]["approved_refund_types"] = "return_refund"
    assert not refund_decision(order)["allowed"]
    order["metadata"]["after_sale_review"] = "approved"
    assert not refund_decision(order)["allowed"]


def test_planner_remaps_condition_and_output_reference_ids():
    planner = PlannerService(tool_registry=build_default_tool_registry())
    plan = planner._normalize_llm_plan(payload={"steps": [
        {"step_id": "lookup", "title": "query", "goal": "query", "action_type": "tool",
         "tool_name": "query_order_status", "arguments": {"order_id": "202606040003"}},
        {"step_id": "write", "title": "refund", "goal": "refund", "action_type": "tool",
         "tool_name": "create_refund_case", "depends_on": ["lookup"],
         "arguments": {"reason": "故障", "refund_type": "return_refund"},
         "conditions": [{"step_id": "lookup", "path": "data.found", "value": True}],
         "argument_refs": {"order_id": {"step_id": "lookup", "path": "data.order_id"}}},
    ]}, request=ChatRequest(user_id="u001", question="test"), conversation_id="c1")
    assert plan.steps[1].conditions[0].step_id == "s1"
    assert plan.steps[1].argument_refs["order_id"].step_id == "s1"
    assert plan.steps[1].requires_confirmation


@pytest.mark.parametrize("facts,expected", [
    ({"found": False}, "finalize"),
    ({"found": True, "status": "shipped"}, "finalize"),
    ({"found": True, "status": "delivered", "metadata": {}}, "finalize"),
    (None, "create_pending_action"),
])
@pytest.mark.asyncio
async def test_real_graph_executor_blocks_or_prepares_refund_from_business_outcomes(facts, expected):
    facts = facts or eligible_order()
    registry = build_default_tool_registry()
    planner = PlannerService(tool_registry=registry)
    llm = AsyncMock()
    plan, _ = await planner.build_plan(request=ChatRequest(user_id="u001",
        question="查询订单202606040003，如果符合要求就申请退款"),
        conversation_id="c1", llm_client=llm, model="test")
    llm.chat.assert_not_called()
    nodes = CustomerServiceGraphNodes.__new__(CustomerServiceGraphNodes)
    nodes._settings = Settings(_env_file=None, mcp_after_sales_enabled=False, plan_max_tool_calls=6)
    nodes._tool_registry = registry
    gateway = SimpleNamespace(query_order_status=AsyncMock(return_value=facts))
    nodes._tool_context = ToolExecutionContext("default", "u001", "c1", object(), object(), gateway)
    nodes._trace_service = SimpleNamespace(step=AsyncMock())
    state = {"plan": plan.model_dump(), "run_id": "r1", "plan_observations": [], "executed_plan_steps": []}
    for _ in range(10):
        command = await nodes.execute_plan_step(state)
        state.update(command.update or {})
        if command.goto != "execute_plan_step":
            break
    assert command.goto == expected
    if expected == "create_pending_action":
        assert state["active_tool_name"] == "create_refund_case"
    else:
        assert not state.get("active_tool_name")
        assert any(step["status"] == "not_satisfied" for step in state["plan"]["steps"])


def test_conditions_and_output_references_use_real_typed_results():
    step = PlanStep(step_id="b", title="b", goal="b", action_type="tool", depends_on=["a"],
        conditions=[StepCondition(step_id="a", path="data.found", value=True)],
        argument_refs={"order_id": OutputReference(step_id="a", path="data.order_id")})
    observation = {"step_id": "a", "outcome": ToolOutcome.from_payload({"found": True, "order_id": "owned"}).model_dump()}
    assert prepare_step(step, [observation])[:2] == (True, {"order_id": "owned"})
    assert not prepare_step(step, [])[0]
    observation["outcome"]["data"]["found"] = 1
    assert not prepare_step(step, [observation])[0]
    with pytest.raises(ValidationError):
        OutputReference(step_id="a", path="__import__('os').system('anything')")


@pytest.mark.asyncio
async def test_registry_rejects_direct_writes_and_parameter_substitution():
    handler = AsyncMock(return_value={"ticket_id": "t1"})
    registry = ToolRegistry()
    registry.register(ToolSpec("write", "write", {"type": "object"}, handler, read_only=False))
    context = ToolExecutionContext("default", "u001", "c1", object(), object())
    with pytest.raises(AppError, match="批准"):
        await registry.execute_dict(name="write", arguments={"amount": 1}, context=context)
    context.confirmation_id = "approval-1"
    context.execution_grant = registry.issue_execution_grant(name="write", arguments={"amount": 1}, context=context)
    with pytest.raises(AppError):
        await registry.execute_dict(name="write", arguments={"amount": 2}, context=context)
    context.user_id = "u002"
    with pytest.raises(AppError):
        await registry.execute_dict(name="write", arguments={"amount": 1}, context=context)
    handler.assert_not_called()
    context.user_id = "u001"
    assert (await registry.execute_dict(name="write", arguments={"amount": 1}, context=context))["ticket_id"] == "t1"


@pytest.mark.asyncio
async def test_read_retry_is_bounded_and_business_failure_is_not_execution_error():
    registry = ToolRegistry()
    handler = AsyncMock(side_effect=[TimeoutError(), {"found": False}])
    registry.register(ToolSpec("read", "read", {"type": "object"}, handler))
    context = ToolExecutionContext("default", "u001", "c1", object(), object())
    outcome = await registry.execute_outcome(name="read", arguments={}, context=context, max_attempts=100)
    assert outcome.execution_status == "success"
    assert outcome.business_status == "not_satisfied" and outcome.attempts == 2
    assert handler.await_count == 2


def test_mcp_error_flag_cannot_masquerade_as_a_successful_ticket():
    with pytest.raises(AppError) as error:
        _normalize_tool_result(SimpleNamespace(isError=True, structuredContent={"ticket_id": "fake"}))
    assert error.value.code == "mcp_tool_error"


def test_approval_token_binds_complete_normalized_action(monkeypatch):
    from after_sales_mcp.config import get_settings
    from after_sales_mcp.security import verify_approval_token
    from customer_service_app.infrastructure.mcp.approval import create_approval_token

    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///unused")
    monkeypatch.setenv("APPROVAL_SIGNING_SECRET", "test-secret")
    get_settings.cache_clear()
    arguments = {"order_id": "owned", "reason": "故障", "refund_type": "return_refund"}
    token = create_approval_token(settings=Settings(_env_file=None, mcp_approval_signing_secret="test-secret"),
        confirmation_id="op-1", tenant_id="default", user_id="u001", tool_name="create_refund_case",
        arguments=arguments, conversation_id="c1")
    verify_approval_token(token=token, tenant_id="default", user_id="u001", tool_name="create_refund_case",
                          arguments=arguments, conversation_id="c1")
    with pytest.raises(ValueError, match="arguments"):
        verify_approval_token(token=token, tenant_id="default", user_id="u001", tool_name="create_refund_case",
                              arguments={**arguments, "order_id": "other"}, conversation_id="c1")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_response_loss_is_reconciled_without_resubmitting_the_write():
    from jose import jwt
    from customer_service_app.services.business_gateway import BusinessGateway

    operation = "stable-operation"
    client = SimpleNamespace(call_tool=AsyncMock(side_effect=[TimeoutError(), {
        "found": True, "operation_id": operation, "ticket_id": "committed-ticket",
    }]))
    token = jwt.encode({"confirmation_id": operation}, "test-only", algorithm="HS256")
    gateway = BusinessGateway(object(), mcp_client=client)
    result = await gateway._call_mcp(name="create_refund_case", arguments={
        "tenant_id": "default", "user_id": "u001", "approval_token": token,
    })
    assert result["reconciled"] is True
    assert [call.kwargs["name"] for call in client.call_tool.await_args_list] == ["create_refund_case", "query_operation_status"]


@pytest.mark.asyncio
async def test_unresolved_response_loss_is_not_reported_as_failure_or_success():
    from jose import jwt
    from customer_service_app.services.business_gateway import BusinessGateway

    client = SimpleNamespace(call_tool=AsyncMock(side_effect=[TimeoutError(), {"found": False}]))
    gateway = BusinessGateway(object(), mcp_client=client)
    with pytest.raises(AppError) as error:
        await gateway._call_mcp(name="create_refund_case", arguments={"tenant_id": "default", "user_id": "u001",
            "approval_token": jwt.encode({"confirmation_id": "op-uncertain"}, "test-only", algorithm="HS256")})
    assert error.value.code == "operation_uncertain"


@pytest.mark.asyncio
async def test_rejection_overwrites_old_checkpoint_approval_when_retrying_failed_node():
    from customer_service_app.workflows.runtime import CustomerServiceGraphRuntime

    graph = SimpleNamespace(ainvoke=AsyncMock(return_value={"status": "completed"}))
    runtime = CustomerServiceGraphRuntime(settings=Settings(_env_file=None), graph=graph)
    decision = {"confirmation_id": "same-action", "decision": "reject"}
    await runtime.resume(thread_id="same-thread", decision=decision, context=object())
    command = graph.ainvoke.call_args.args[0]
    assert command.update["confirmation_decision"] == decision
    assert command.resume == decision
