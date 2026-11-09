"""Mock services + actual compiled LangGraph, no model quota or business writes."""
import asyncio
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from pydantic import ValidationError

from customer_service_app.core.config import Settings
from customer_service_app.core.exceptions import AppError, PermissionDeniedError
from customer_service_app.domain.schemas import ChatRequest, ChatResponse
from customer_service_app.domain.streaming import EventFactory, StreamEvent
from customer_service_app.infrastructure.llm.openai_compatible import OpenAICompatibleLLMClient
from customer_service_app.services.customer_service_agent import CustomerServiceAgent
from customer_service_app.services.stream_service import StreamSupervisor, Subscription
from customer_service_app.services.business_policy_service import BusinessPolicyService
from customer_service_app.services.tool_registry import ToolExecutionContext
from customer_service_app.tools.default_registry import build_default_tool_registry
from customer_service_app.workflows.context import CustomerServiceGraphContext
from customer_service_app.workflows.customer_service_graph import build_customer_service_graph
from customer_service_app.workflows.runtime import CustomerServiceGraphRuntime


class GatedNodes:
    def __init__(self, fail=False):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.finished = False
        self.fail = fail

    async def prepare(self, state):
        return Command(update={"run_id": "r", "conversation_id": "c", "status": "running"}, goto="rewrite")

    async def rewrite(self, state):
        self.entered.set()
        await self.release.wait()
        if self.fail:
            raise ValueError("API_KEY=NEVER-SEND-THIS")
        return Command(update={"final_answer": "真实结果"}, goto="persist")

    async def persist(self, state):
        self.finished = True
        return {"status": "completed"}

    @staticmethod
    def to_response(state):
        return ChatResponse(conversation_id="c", thread_id=state["thread_id"], run_id="r",
                            answer=state["final_answer"], status=state["status"])


def setup_agent(nodes):
    runtime = CustomerServiceGraphRuntime(settings=Settings(),
        graph=build_customer_service_graph(InMemorySaver()))
    trace = SimpleNamespace(get_idempotent_response=AsyncMock(return_value=None), save_response=AsyncMock(),
        get_run=AsyncMock(return_value=SimpleNamespace(id="r")), finish_failed=AsyncMock())
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    agent = CustomerServiceAgent(session=session, graph_runtime=runtime, graph_nodes=nodes,
        confirmation_service=None, human_support_service=SimpleNamespace(get_active_for_customer=AsyncMock(return_value=None)),
        trace_service=trace)
    return agent, runtime, trace, session


async def test_actual_graph_first_completed_node_arrives_before_run_finishes():
    nodes = GatedNodes()
    agent, _, trace, session = setup_agent(nodes)
    frames = agent.stream_events(ChatRequest(user_id="u", question="test"), EventFactory())
    first = await asyncio.wait_for(anext(frames), 2)
    assert first.event_type == "run_started" and first.run_id == "r"
    second = await asyncio.wait_for(anext(frames), 2)
    assert second.event_type == "node_completed" and second.payload.node == "prepare"
    assert not nodes.finished  # A gated real graph node has not completed.
    session.commit.assert_awaited()
    nodes.release.set()
    events = [first, second, *[e async for e in frames]]
    assert events[-1].event_type == "run_completed"
    assert events[-1].payload.persisted is True
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))
    assert len({e.event_id for e in events}) == len(events)
    for event in events:
        assert StreamEvent.model_validate_json(event.model_dump_json()) == event
        assert event.timestamp.tzinfo is not None
    trace.save_response.assert_awaited_once()


async def test_node_error_is_sanitized_and_persisted_as_failed():
    nodes = GatedNodes(fail=True)
    nodes.release.set()
    agent, _, trace, session = setup_agent(nodes)
    events = [e async for e in agent.stream_events(ChatRequest(user_id="u", question="test"), EventFactory())]
    assert events[-1].event_type == "run_failed"
    assert not any(e.event_type == "run_completed" for e in events)
    assert "NEVER-SEND-THIS" not in "".join(e.sse() for e in events)
    session.rollback.assert_awaited_once()
    trace.finish_failed.assert_awaited_once()


async def test_knowledge_event_uses_allowlist_not_raw_graph_update():
    class KnowledgeNodes(GatedNodes):
        async def rewrite(self, state):
            return Command(goto="retrieve")
        async def retrieve(self, state):
            return Command(update={"final_answer": "public", "knowledge": [{
                "id": "k", "source": "policy.md", "title": "政策", "content": "公开条款",
                "metadata": {"api_key": "PRIVATE-KNOWLEDGE-METADATA"}, "score": 0.9,
            }]}, goto="persist")
    agent, _, _, _ = setup_agent(KnowledgeNodes())
    events = [e async for e in agent.stream_events(ChatRequest(user_id="u", question="test"), EventFactory())]
    knowledge = next(e for e in events if e.event_type == "knowledge_ready")
    assert knowledge.payload.knowledge[0].content == "公开条款"
    assert "PRIVATE-KNOWLEDGE-METADATA" not in "".join(e.sse() for e in events)
    assert events[-1].event_type == "run_completed"


def test_event_contract_rejects_sensitive_extra_fields_and_wrong_payload():
    f = EventFactory()
    with pytest.raises(ValidationError):
        f.make("node_completed", {"node": "decide", "state": {"api_key": "secret"}})
    with pytest.raises(ValidationError):
        f.make("answer_delta", {"node": "decide"})


async def test_disconnect_does_not_cancel_worker_or_close_its_session():
    release = asyncio.Event()
    closed = asyncio.Event()
    completed = asyncio.Event()

    @asynccontextmanager
    async def session_factory():
        try:
            yield object()
        finally:
            closed.set()

    class Agent:
        async def stream_events(self, request, factory):
            yield factory.make("node_completed", {"node": "prepare"})
            await release.wait()
            completed.set()
            yield factory.make("run_completed", {"answer": "done", "status": "completed"})

    supervisor = StreamSupervisor(session_factory)
    sub = supervisor.start(SimpleNamespace(build_agent=lambda _: Agent()), ChatRequest(user_id="u", question="test"))
    frames = sub.frames(heartbeat_seconds=0.01)
    await anext(frames)
    await frames.aclose()
    assert not closed.is_set() and not completed.is_set()
    release.set()
    await asyncio.wait_for(completed.wait(), 2)
    await supervisor.close()
    assert closed.is_set() and not sub.attached and sub.queue.empty()


async def test_slow_subscription_is_bounded_and_reports_unknown_without_blocking_worker():
    sub = Subscription(EventFactory(), capacity=1)
    sub.publish(sub.factory.make("node_completed", {"node": "prepare"}))
    sub.publish(sub.factory.make("node_completed", {"node": "rewrite"}))
    assert sub.queue.qsize() == 1
    frames = sub.frames()
    frame = await anext(frames)
    assert "stream_interrupted" in frame and '"status":"unknown"' in frame
    await frames.aclose()


async def test_shutdown_cancels_owned_worker_after_grace_period():
    closed = asyncio.Event()
    @asynccontextmanager
    async def session_factory():
        try:
            yield object()
        finally:
            closed.set()
    class Agent:
        async def stream_events(self, request, factory):
            await asyncio.Event().wait()
            yield factory.make("heartbeat", {})
    supervisor = StreamSupervisor(session_factory)
    supervisor.start(SimpleNamespace(build_agent=lambda _: Agent()), ChatRequest(user_id="u", question="test"))
    await asyncio.sleep(0)
    await supervisor.close(timeout=0)
    assert closed.is_set() and not supervisor.tasks


async def test_shutdown_records_unknown_instead_of_claiming_business_cancellation():
    run = SimpleNamespace(status="running")
    session = SimpleNamespace(get=AsyncMock(return_value=run), commit=AsyncMock())
    @asynccontextmanager
    async def factory():
        yield session
    await StreamSupervisor(factory)._mark_unknown("run")
    assert run.status == "unknown" and run.error_code == "stream_shutdown_unknown"
    session.commit.assert_awaited_once()


async def test_confirmation_uses_same_conversation_lock_as_stream_worker():
    agent, _, _, _ = setup_agent(GatedNodes())
    held = []
    @asynccontextmanager
    async def hold(**kwargs):
        held.append(kwargs)
        yield
    agent._request_lock = SimpleNamespace(hold=hold)
    agent._confirmation_service = SimpleNamespace(get_owned=AsyncMock(return_value=SimpleNamespace(
        conversation_id="conversation", langgraph_thread_id="thread")))
    agent._resume_confirmation_unlocked = AsyncMock(return_value="result")
    assert await agent.resume_confirmation(tenant_id="tenant", user_id="user", confirmation_id="action",
                                          decision="approve", reason=None) == "result"
    assert held[0]["conversation_id"] == "conversation"
    assert held[0]["thread_id"] == "thread"


async def test_thread_ownership_checked_before_graph_executes():
    nodes = GatedNodes()
    nodes.release.set()
    _, runtime, _, _ = setup_agent(nodes)
    async for _ in runtime.stream(request_payload={"tenant_id": "a", "user_id": "u", "conversation_id": "c"},
            context=CustomerServiceGraphContext(nodes=nodes), thread_id="owned"):
        pass
    with pytest.raises(PermissionDeniedError):
        async for _ in runtime.stream(request_payload={"tenant_id": "b", "user_id": "u", "conversation_id": "c"},
                context=CustomerServiceGraphContext(nodes=nodes), thread_id="owned"):
            pass


async def test_native_llm_stream_emits_provider_deltas_usage_and_no_reasoning():
    create = AsyncMock()
    class ProviderStream:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def __aiter__(self):
            yield SimpleNamespace(usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content="你好", reasoning_content="PRIVATE"))])
            yield SimpleNamespace(usage=SimpleNamespace(prompt_tokens=8, completion_tokens=2, total_tokens=10), choices=[])
    create.return_value = ProviderStream()
    llm = OpenAICompatibleLLMClient(Settings())
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    parts = [p async for p in llm.stream_response([], model="configured-model")]
    assert [p.content for p in parts] == ["你好", ""]
    assert parts[-1].total_tokens == 10
    assert create.call_args.kwargs["stream"] is True
    assert create.call_args.kwargs["model"] == "configured-model"


async def test_native_stream_error_is_not_a_retryable_graph_external_error():
    llm = OpenAICompatibleLLMClient(Settings())
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=ValueError("secret")))))
    with pytest.raises(AppError, match="答案生成中断") as exc:
        async for _ in llm.stream_response([], model="model"):
            pass
    assert exc.value.code == "answer_stream_failed"


async def test_preapproved_action_rechecks_current_facts_before_a_write():
    # Mock facts only. The three real seeded orders are never changed by this test.
    gateway = SimpleNamespace(query_order_status=AsyncMock(return_value={"found": True, "status": "delivered",
        "metadata": {"after_sale_review": {"status": "approved", "policy_id": "p", "policy_version": "1",
            "evidence_verified": True, "category_checks_passed": True, "approved_refund_types": ["return_refund"],
            "valid_until": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}}}),
        create_refund_case=AsyncMock())
    context = ToolExecutionContext("default", "u001", "c", object(), object(), business_gateway=gateway)
    registry = build_default_tool_registry()
    args = {"order_id": "owned", "reason": "fault", "refund_type": "return_refund"}
    assert (await BusinessPolicyService().check(tool_name="create_refund_case", arguments=args, context=context))["allowed"]
    context.confirmation_id = "approved-operation"
    context.execution_grant = registry.issue_execution_grant(name="create_refund_case", arguments=args, context=context)
    gateway.query_order_status.return_value = {"found": True, "status": "shipped"}
    with pytest.raises(AppError) as exc:
        await registry.execute_dict(name="create_refund_case", arguments=args, context=context)
    assert exc.value.code == "business_precondition_failed"
    gateway.create_refund_case.assert_not_called()


async def test_stream_preserves_human_message_path_without_creating_an_agent_run():
    agent, runtime, trace, _ = setup_agent(GatedNodes())
    runtime.stream = AsyncMock(side_effect=AssertionError("Human mode must not start a graph"))
    agent._human_support_service = SimpleNamespace(
        get_active_for_customer=AsyncMock(return_value=SimpleNamespace(assigned_agent_id="agent")),
        accept_customer_message=AsyncMock(), to_view=lambda _: None)
    events = [e async for e in agent.stream_events(ChatRequest(user_id="u", question="more details",
        conversation_id="c", metadata={"idempotency_key": "human-request"}), EventFactory("c"))]
    assert [e.event_type for e in events] == ["run_completed"]
    assert events[0].run_id is None and events[0].payload.status == "human_active"
    agent._human_support_service.accept_customer_message.assert_awaited_once()
    trace.save_response.assert_not_called()
