from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from customer_service_app.main import create_app
from customer_service_app.api.dependencies import get_current_principal, get_customer_service_agent
from customer_service_app.core.security import CurrentPrincipal
from customer_service_app.core.config import Settings
from customer_service_app.domain.schemas import GraphStateView
from customer_service_app.workflows.runtime import CustomerServiceGraphRuntime


@pytest.mark.parametrize("tenant,expected", [("tenant-a", 200), ("tenant-b", 403)])
def test_operator_graph_inspection_is_tenant_scoped(tenant, expected):
    app = create_app()
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        subject="operator", tenant_id="tenant-a", roles=frozenset({"operator"}))
    app.dependency_overrides[get_customer_service_agent] = lambda: SimpleNamespace(graph_state=AsyncMock(
        return_value=GraphStateView(thread_id="t", status="running", values={"tenant_id": tenant, "user_id": "u"})))
    assert TestClient(app).get("/api/v1/graph/threads/t").status_code == expected


async def test_sanitized_snapshot_retains_only_identity_not_raw_request():
    graph = SimpleNamespace(aget_state=AsyncMock(return_value=SimpleNamespace(
        values={"request": {"tenant_id": "tenant-a", "user_id": "u", "metadata": {"secret": "private"}}, "status": "running"},
        tasks=[], next=[])))
    runtime = CustomerServiceGraphRuntime(settings=Settings(), graph=graph)
    state = await runtime.get_state(thread_id="t")
    assert state.values["tenant_id"] == "tenant-a" and state.values["user_id"] == "u"
    assert "request" not in state.values and "private" not in state.model_dump_json()
