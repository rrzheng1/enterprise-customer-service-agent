"""Read-only product adapters. Business writes remain in the existing Agent APIs."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service_app.api.dependencies import get_current_principal, require_roles
from customer_service_app.core.config import get_settings
from customer_service_app.core.exceptions import PermissionDeniedError
from customer_service_app.core.security import CurrentPrincipal, authorize_identity
from customer_service_app.domain.confirmations import PendingActionView
from customer_service_app.domain.schemas import ChatResponse, ConversationMessageView, ConversationView
from customer_service_app.infrastructure.db.models import AgentRun, Conversation, SupportTicket
from customer_service_app.infrastructure.db.session import get_db_session
from customer_service_app.infrastructure.db.repositories import PendingActionRepository
from customer_service_app.services.confirmation_service import ConfirmationService
from customer_service_app.services.conversation_service import ConversationService

router = APIRouter(tags=["workspace"])
ops_router = APIRouter(prefix="/ops/api", tags=["ops"])


class SessionView(BaseModel):
    authenticated: bool
    development_mode: bool
    tenant_id: str
    user_id: str
    display_name: str
    roles: list[str]
    api_prefix: str


class TicketView(BaseModel):
    id: str
    category: str
    title: str
    status: str
    priority: str
    order_id: str | None = None
    created_at: datetime | None = None


class RunSummaryView(BaseModel):
    id: str
    conversation_id: str | None
    status: str
    model: str | None
    total_tokens: int
    error_code: str | None
    started_at: datetime | None


class ConversationWorkspaceView(BaseModel):
    conversation: ConversationView
    messages: list[ConversationMessageView]
    pending_actions: list[PendingActionView]
    tickets: list[TicketView]
    responses: dict[str, ChatResponse] = Field(default_factory=dict)
    runs: list["CustomerRunView"] = Field(default_factory=list)


class CustomerRunView(BaseModel):
    id: str
    request_id: str | None = None
    status: str
    error_code: str | None = None
    started_at: datetime | None = None


@router.get("/session", response_model=SessionView)
async def current_session(
    workspace: Literal["customer", "operations"] = "customer",
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> SessionView:
    settings = get_settings()
    development = not principal.authenticated and settings.runtime_env.lower() in {"local", "development", "test"}
    if development:
        operator = workspace == "operations"
        return SessionView(authenticated=False, development_mode=True, tenant_id="default",
            user_id="agent-001" if operator else "u001", display_name="演示坐席" if operator else "演示客户",
            roles=["agent", "operator"] if operator else ["customer"], api_prefix=settings.api_prefix)
    if workspace == "operations" and not principal.has_any_role("agent", "operator", "admin"):
        raise PermissionDeniedError("Current role cannot access the operations workspace")
    return SessionView(authenticated=True, development_mode=False, tenant_id=principal.tenant_id,
        user_id=principal.subject, display_name=principal.subject, roles=sorted(principal.roles), api_prefix=settings.api_prefix)


@router.get("/conversations/{conversation_id}/workspace", response_model=ConversationWorkspaceView)
async def conversation_workspace(
    conversation_id: str, tenant_id: str, user_id: str,
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(require_roles("customer", "agent", "operator", "admin")),
) -> ConversationWorkspaceView:
    tenant_id, user_id = authorize_identity(principal, tenant_id=tenant_id, user_id=user_id)
    service = ConversationService(session)
    conversation, _ = await service.get_conversation_detail(tenant_id=tenant_id, user_id=user_id,
                                                            conversation_id=conversation_id)
    messages = await service.list_message_records(conversation_id=conversation_id)
    pending_records = await PendingActionRepository(session).list_pending_for_conversation(
        tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)
    confirmation_service = ConfirmationService(settings=get_settings(), session=session)
    pending = [confirmation_service.to_view(item) for item in pending_records]
    # MySQL's current timestamp columns have second precision. Restore turn order on ties.
    messages.sort(key=lambda item: (item.created_at, 0 if item.role == "user" else 1))
    tickets = (await session.execute(select(SupportTicket).where(
        SupportTicket.conversation_id == conversation_id, SupportTicket.tenant_id == tenant_id,
        SupportTicket.user_id == user_id).order_by(SupportTicket.created_at.desc()).limit(100))).scalars().all()
    runs = (await session.execute(select(AgentRun).where(
        AgentRun.conversation_id == conversation_id, AgentRun.tenant_id == tenant_id,
        AgentRun.user_id == user_id).order_by(AgentRun.started_at.desc()).limit(30))).scalars().all()
    responses: dict[str, ChatResponse] = {}
    for run in runs:
        if run.response_json and run.response_json.get("conversation_id") == conversation_id:
            responses[run.id] = ChatResponse.model_validate(run.response_json)
    return ConversationWorkspaceView(
        conversation=ConversationView(id=conversation.id, tenant_id=tenant_id, user_id=user_id,
            title=conversation.title, status=conversation.status, service_mode=conversation.service_mode),
        messages=[ConversationMessageView(id=item.id, role=item.role, content=item.content,
            metadata=item.metadata_json or {}, created_at=item.created_at) for item in messages],
        pending_actions=[item for item in pending if item.conversation_id == conversation_id],
        tickets=[TicketView(id=item.id, category=item.category, title=item.title, status=item.status,
            priority=item.priority, order_id=(item.metadata_json or {}).get("order_id"), created_at=item.created_at) for item in tickets],
        responses=responses,
        runs=[CustomerRunView(id=item.id, request_id=item.request_id, status=item.status, error_code=item.error_code,
                              started_at=item.started_at) for item in runs],
    )


@ops_router.get("/conversations", response_model=list[ConversationView])
async def operations_conversations(
    tenant_id: str, user_id: str | None = None, limit: int = Query(60, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(require_roles("agent", "operator", "admin")),
) -> list[ConversationView]:
    tenant_id, _ = authorize_identity(principal, tenant_id=tenant_id)
    statement = select(Conversation).where(Conversation.tenant_id == tenant_id)
    if user_id:
        statement = statement.where(Conversation.user_id == user_id)
    items = (await session.execute(statement.order_by(Conversation.updated_at.desc()).limit(limit))).scalars().all()
    return [ConversationView(id=item.id, tenant_id=item.tenant_id, user_id=item.user_id,
        title=item.title, status=item.status, service_mode=item.service_mode) for item in items]


@ops_router.get("/runs", response_model=list[RunSummaryView])
async def operations_runs(
    tenant_id: str, conversation_id: str | None = None, limit: int = Query(40, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
    principal: CurrentPrincipal = Depends(require_roles("operator", "admin")),
) -> list[RunSummaryView]:
    tenant_id, _ = authorize_identity(principal, tenant_id=tenant_id)
    statement = select(AgentRun).where(AgentRun.tenant_id == tenant_id)
    if conversation_id:
        statement = statement.where(AgentRun.conversation_id == conversation_id)
    items = (await session.execute(statement.order_by(AgentRun.started_at.desc()).limit(limit))).scalars().all()
    return [RunSummaryView(id=item.id, conversation_id=item.conversation_id, status=item.status,
        model=item.model, total_tokens=item.total_tokens, error_code=item.error_code, started_at=item.started_at) for item in items]
