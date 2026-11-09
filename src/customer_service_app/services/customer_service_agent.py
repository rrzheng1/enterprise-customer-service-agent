from __future__ import annotations

from collections.abc import AsyncIterator
import logging
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from customer_service_app.core.exceptions import AppError
from customer_service_app.domain.schemas import ChatRequest, ChatResponse, GraphStateView
from customer_service_app.domain.confirmations import PendingActionView
from customer_service_app.infrastructure.cache.distributed_lock import RedisConversationLock
from customer_service_app.services.confirmation_service import ConfirmationService
from customer_service_app.services.human_support_service import HumanSupportService
from customer_service_app.services.trace_service import TraceService
from customer_service_app.workflows.context import CustomerServiceGraphContext
from customer_service_app.workflows.nodes import CustomerServiceGraphNodes
from customer_service_app.workflows.runtime import CustomerServiceGraphRuntime


class CustomerServiceAgent:
    """客服 Agent 的 API 门面。

    这一层可以理解为 Java 里的 Application Service / Facade：
    - API 路由只调用 Agent，不直接碰 LLM、RAG、Tool、LangGraph 节点。
    - Agent 负责事务边界、Graph 启动、Graph 恢复、响应对象转换。
    - 真正的业务步骤在 CustomerServiceGraphNodes 中，不写在这里。
    """

    def __init__(
        self,
        *,
        session: AsyncSession,
        graph_runtime: CustomerServiceGraphRuntime,
        graph_nodes: CustomerServiceGraphNodes,
        confirmation_service: ConfirmationService,
        human_support_service: HumanSupportService,
        trace_service: TraceService,
        request_lock: RedisConversationLock | None = None,
    ):
        self._session = session

        self._graph_runtime = graph_runtime

        self._graph_nodes = graph_nodes

        self._confirmation_service = confirmation_service
        self._human_support_service = human_support_service
        self._trace_service = trace_service
        self._request_lock = request_lock

        self._graph_context = CustomerServiceGraphContext(nodes=graph_nodes)

    async def answer(self, request: ChatRequest) -> ChatResponse:
        """按幂等键复用已落库响应，并串行保护同一会话的 Graph 状态。"""
        async with self._lock_scope(request):
            idempotency_key = self._idempotency_key(request)
            if idempotency_key:
                cached_response = await self._trace_service.get_idempotent_response(
                    tenant_id=request.tenant_id,
                    user_id=request.user_id,
                    request_id=idempotency_key,
                )
                if cached_response:
                    return ChatResponse.model_validate(cached_response)

            response = await self._answer_unlocked(request)
            if idempotency_key and response.run_id:
                await self._trace_service.save_response(
                    run_id=response.run_id,
                    response=response.model_dump(mode="json"),
                )
                await self._session.commit()
            return response

    async def _answer_unlocked(self, request: ChatRequest) -> ChatResponse:
        """启动一轮普通聊天请求。

        这里的“启动”不是直接调用大模型，而是把请求交给 LangGraph。
        Graph 可能完整跑完，也可能在 HIL 节点 interrupt 暂停。
        """
        try:
            if request.conversation_id:
                handoff = await self._human_support_service.get_active_for_customer(
                    tenant_id=request.tenant_id,
                    user_id=request.user_id,
                    conversation_id=request.conversation_id,
                )
                if handoff is not None:
                    await self._human_support_service.accept_customer_message(
                        handoff=handoff,
                        content=request.question,
                        metadata=request.metadata,
                    )
                    await self._session.commit()
                    return ChatResponse(
                        conversation_id=request.conversation_id,
                        thread_id=request.thread_id,
                        answer=(
                            "消息已发送给人工客服，当前会话由人工坐席处理。"
                            if handoff.assigned_agent_id
                            else "已进入人工客服队列，消息已保存，坐席接入后会继续处理。"
                        ),
                        status=(
                            "human_active" if handoff.assigned_agent_id else "waiting_human"
                        ),
                        service_mode="human",
                        human_handoff=self._human_support_service.to_view(handoff),
                    )

            request_payload = request.model_dump(mode="json")

            state = await self._graph_runtime.invoke(
                request_payload=request_payload,
                context=self._graph_context,
                thread_id=request.thread_id,
            )

            await self._session.commit()

            return self._graph_nodes.to_response(state)
        except Exception:
            await self._session.rollback()
            raise

    @asynccontextmanager
    async def _lock_scope(self, request: ChatRequest) -> AsyncIterator[None]:
        """在启用 Redis 锁时保护同一会话，否则保持本地开发兼容性。"""
        if self._request_lock is None:
            yield
            return

        async with self._request_lock.hold(
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            thread_id=request.thread_id,
            request_id=self._idempotency_key(request),
        ):
            yield

    @staticmethod
    def _idempotency_key(request: ChatRequest) -> str | None:
        """读取客户端幂等键，不把普通 request_id 误当成可重放键。"""
        value = str(request.metadata.get("idempotency_key") or "").strip()
        return value or None

    async def resume_confirmation(
        self,
        *,
        tenant_id: str,
        user_id: str,
        confirmation_id: str,
        decision: str,
        reason: str | None,
    ) -> ChatResponse:
        """与聊天共用会话锁，防止审批抢在流式线程完成 checkpoint 暂停前恢复。"""
        if self._request_lock is None:
            return await self._resume_confirmation_unlocked(
                tenant_id=tenant_id,
                user_id=user_id,
                confirmation_id=confirmation_id,
                decision=decision,
                reason=reason,
            )

        action = await self._confirmation_service.get_owned(
            tenant_id=tenant_id, user_id=user_id, action_id=confirmation_id)
        async with self._request_lock.hold(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=action.conversation_id,
            thread_id=action.langgraph_thread_id,
            request_id=f"confirmation:{confirmation_id}",
        ):
            return await self._resume_confirmation_unlocked(
                tenant_id=tenant_id,
                user_id=user_id,
                confirmation_id=confirmation_id,
                decision=decision,
                reason=reason,
            )

    async def _resume_confirmation_unlocked(
        self,
        *,
        tenant_id: str,
        user_id: str,
        confirmation_id: str,
        decision: str,
        reason: str | None,
    ) -> ChatResponse:
        """根据用户确认/拒绝结果恢复被 interrupt 暂停的 Graph。

        注意：恢复必须使用确认单里保存的 langgraph_thread_id。
        这能确保恢复的是原来那条暂停的执行链路，而不是重新发起一次聊天。
        """
        try:
            action = await self._confirmation_service.get_owned(
                tenant_id=tenant_id,
                user_id=user_id,
                action_id=confirmation_id,
            )
            if not action.langgraph_thread_id:
                raise AppError(
                    "Confirmation is not bound to a graph thread",
                    code="confirmation_thread_missing",
                    status_code=409,
                )

            decision_payload = {
                "confirmation_id": confirmation_id,
                "decision": decision,
                "reason": reason,
            }
            state = await self._graph_runtime.resume(
                thread_id=action.langgraph_thread_id,
                decision=decision_payload,
                context=self._graph_context,
            )
            await self._session.commit()
            return self._graph_nodes.to_response(state)
        except Exception:
            await self._session.rollback()
            raise

    async def graph_state(self, *, thread_id: str) -> GraphStateView:
        """读取指定 LangGraph thread 的 checkpoint 快照。"""
        return await self._graph_runtime.get_state(thread_id=thread_id)

    async def get_confirmation(
        self,
        *,
        tenant_id: str,
        user_id: str,
        confirmation_id: str,
    ) -> PendingActionView:
        """查询当前用户自己的待确认动作。"""
        action = await self._confirmation_service.get_owned(
            tenant_id=tenant_id,
            user_id=user_id,
            action_id=confirmation_id,
        )
        return self._confirmation_service.to_view(action)

    async def stream_events(self, request: ChatRequest, events) -> AsyncIterator:
        """Live graph execution with an independent worker-owned session and durable terminal data."""
        try:
            async with self._lock_scope(request):
                key = self._idempotency_key(request)
                cached = await self._trace_service.get_idempotent_response(
                    tenant_id=request.tenant_id, user_id=request.user_id, request_id=key,
                ) if key else None
                response = ChatResponse.model_validate(cached) if cached else None
                if response is None and request.conversation_id:
                    handoff = await self._human_support_service.get_active_for_customer(
                        tenant_id=request.tenant_id, user_id=request.user_id,
                        conversation_id=request.conversation_id)
                    if handoff is not None:
                        response = await self._answer_unlocked(request)
                if response is None:
                    async for kind, data in self._graph_runtime.stream(
                        request_payload=request.model_dump(mode="json"), context=self._graph_context,
                        thread_id=request.thread_id,
                    ):
                        if kind == "run_started":
                            events.run_id = data["run_id"]
                            events.conversation_id = data["conversation_id"]
                            events.thread_id = data["thread_id"]
                            # Make the run visible to GET workspace while subsequent nodes execute.
                            await self._session.commit()
                            yield events.make(kind, {"status": "running"})
                        elif kind == "_result":
                            response = self._graph_nodes.to_response(data)
                        else:
                            yield events.make(kind, data)
                if response is None:
                    raise AppError("Graph produced no terminal response", code="stream_no_result")
                if response.run_id:
                    await self._trace_service.save_response(run_id=response.run_id,
                        response=response.model_dump(mode="json"))
                await self._session.commit()
                events.run_id = response.run_id
                events.conversation_id = response.conversation_id
                events.thread_id = response.thread_id
                if response.pending_confirmation:
                    a = response.pending_confirmation
                    yield events.make("confirmation_required", {"confirmation": {
                        "id": a.id, "action_type": a.action_type, "tool_name": a.tool_name,
                        "status": a.status, "order_id": a.arguments.get("order_id"),
                        "reason": a.arguments.get("reason")}})
                yield events.make("run_completed", {"status": response.status,
                    "answer": response.answer, "persisted": True})
        except Exception:
            logging.getLogger(__name__).exception("Agent stream failed (run_id=%s)", events.run_id)
            await self._session.rollback()
            if events.run_id:
                run = await self._trace_service.get_run(run_id=events.run_id)
                if run is not None:
                    await self._trace_service.finish_failed(run=run, timer_start=0,
                        error_code="stream_execution_failed", error_message="Agent execution did not complete")
                    await self._session.commit()
            yield events.make("run_failed", {"code": "stream_execution_failed",
                "message": "Agent execution did not complete. Read persisted records before retrying.", "status": "failed"})
