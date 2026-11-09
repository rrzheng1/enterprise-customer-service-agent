"""Bounded, process-local SSE subscriptions; workers outlive HTTP connections.

Not an event log or durable job queue. Workspace is the recovery source of truth.
"""
import asyncio
from collections.abc import AsyncIterator, Callable

from customer_service_app.core.exceptions import AppError
from customer_service_app.domain.streaming import EventFactory, StreamEvent
from customer_service_app.infrastructure.db.models import AgentRun


class Subscription:
    def __init__(self, events: EventFactory, capacity: int = 128):
        self.factory = events
        self.queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=capacity)
        self.done = asyncio.Event()
        self.overflow = False
        self.attached = True

    def publish(self, event: StreamEvent) -> None:
        if not self.attached:
            return
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.overflow = True
            self.attached = False  # Do not block a business transaction on a slow browser.

    async def frames(self, heartbeat_seconds: float = 10) -> AsyncIterator[str]:
        try:
            while not self.done.is_set() or not self.queue.empty():
                if self.overflow:
                    yield self.factory.make("stream_interrupted", {"code": "slow_consumer",
                        "message": "连接接收过慢，请读取已保存的会话结果。", "status": "unknown"}).sse()
                    return
                try:
                    event = await asyncio.wait_for(self.queue.get(), timeout=heartbeat_seconds)
                except TimeoutError:
                    if not self.queue.empty():
                        continue
                    if not self.done.is_set():
                        yield self.factory.make("heartbeat", {}).sse()
                    continue
                yield event.sse()
        finally:
            self.attached = False
            while not self.queue.empty():
                self.queue.get_nowait()


class StreamSupervisor:
    def __init__(self, session_factory: Callable, max_active: int = 64):
        self.session_factory = session_factory
        self.max_active = max_active
        self.tasks: set[asyncio.Task] = set()
        self.closing = False

    def start(self, container, request) -> Subscription:
        if self.closing or len(self.tasks) >= self.max_active:
            raise AppError("当前请求较多，请稍后重试", code="stream_capacity", status_code=503)
        sub = Subscription(EventFactory(request.conversation_id, request.thread_id))
        task = asyncio.create_task(self._work(container, request, sub), name="agent-stream-worker")
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return sub

    async def _work(self, container, request, sub):
        try:
            async with self.session_factory() as session:
                agent = container.build_agent(session)
                async for event in agent.stream_events(request, sub.factory):
                    sub.publish(event)
        except asyncio.CancelledError:
            # Hard shutdown is not a business cancellation; records may be incomplete.
            try:
                await asyncio.wait_for(self._mark_unknown(sub.factory.run_id), timeout=3)
            except Exception:
                pass  # A crashed DB cannot provide proof of a terminal business result.
            sub.publish(sub.factory.make("stream_interrupted", {"code": "server_shutdown",
                "message": "服务正在重启，执行结果需重新核实。", "status": "unknown"}))
            raise
        except Exception:
            sub.publish(sub.factory.make("stream_interrupted", {"code": "stream_worker_failed",
                "message": "连接处理异常，请刷新会话核实实际状态。", "status": "unknown"}))
        finally:
            sub.done.set()

    async def _mark_unknown(self, run_id: str | None) -> None:
        if not run_id:
            return
        async with self.session_factory() as session:
            run = await session.get(AgentRun, run_id)
            durable_pause = run and run.status == "waiting_confirmation" and getattr(run, "response_json", None)
            if run and run.status not in {"success", "failed"} and not durable_pause:
                run.status = "unknown"
                run.error_code = "stream_shutdown_unknown"
                run.error_message = "Execution interrupted during shutdown; reconcile persisted state"
                await session.commit()

    async def close(self, timeout: float = 25) -> None:
        self.closing = True
        if not self.tasks:
            return
        _, pending = await asyncio.wait(list(self.tasks), timeout=timeout)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
