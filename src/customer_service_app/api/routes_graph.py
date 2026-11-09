from __future__ import annotations

from fastapi import APIRouter, Depends

from customer_service_app.api.dependencies import (
    get_customer_service_agent,
    require_roles,
)
from customer_service_app.core.security import CurrentPrincipal, authorize_identity
from customer_service_app.core.exceptions import PermissionDeniedError
from customer_service_app.domain.schemas import GraphStateView
from customer_service_app.services.customer_service_agent import CustomerServiceAgent


router = APIRouter(prefix="/graph", tags=["graph"])
"""Graph 调试接口路由组。

最终路径是 `/api/v1/graph/...`，主要给运营验证台和开发排查使用。
"""


@router.get("/threads/{thread_id}", response_model=GraphStateView)
async def get_graph_thread(
    thread_id: str,
    agent: CustomerServiceAgent = Depends(get_customer_service_agent),
    principal: CurrentPrincipal = Depends(require_roles("operator", "admin")),
) -> GraphStateView:
    """Inspect a sanitized LangGraph checkpoint for operations and debugging."""

    state = await agent.graph_state(thread_id=thread_id)
    tenant_id = state.values.get("tenant_id")
    if tenant_id:
        authorize_identity(
            principal,
            tenant_id=str(tenant_id),
            user_id=str(state.values["user_id"]) if state.values.get("user_id") else None,
        )
    elif state.values and principal.authenticated and not principal.is_platform_admin:
        raise PermissionDeniedError("Cannot verify the owner of this legacy graph state")
    return state
