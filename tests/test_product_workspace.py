"""HTTP authorization checks without models, databases or container dependencies."""
import pytest
from fastapi.testclient import TestClient
from customer_service_app.main import create_app
from customer_service_app.api.dependencies import get_current_principal
from customer_service_app.core.security import CurrentPrincipal
from customer_service_app.core.security import create_access_token
from customer_service_app.core.config import Settings, get_settings


@pytest.fixture
def customer_client():
    app = create_app()
    app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
        subject="u001", tenant_id="default", roles=frozenset({"customer"}))
    # No lifespan: unauthorized requests must fail before opening business services.
    return TestClient(app)


@pytest.mark.parametrize("path", [
    "/api/v1/session?workspace=operations",
    "/ops/api/conversations?tenant_id=default",
    "/ops/api/runs?tenant_id=default",
    "/ops/api/runtime",
    "/api/v1/human-support/queue?tenant_id=default",
])
def test_customer_cannot_open_operator_resources(customer_client, path):
    assert customer_client.get(path).status_code == 403


def test_customer_session_uses_verified_identity(customer_client):
    response = customer_client.get("/api/v1/session?workspace=customer")
    assert response.status_code == 200
    assert response.json()["user_id"] == "u001"
    assert response.json()["development_mode"] is False
    assert response.json()["roles"] == ["customer"]


def test_customer_cannot_assign_handoff(customer_client):
    response = customer_client.post("/api/v1/human-support/any/assign", json={
        "tenant_id": "default", "agent_id": "u001", "expected_version": 1})
    assert response.status_code == 403


def test_signed_customer_token_cannot_escalate_to_operations():
    settings = Settings(runtime_env="production", security_enabled=True,
                        jwt_secret_key="product-test-signing-key-not-a-deployment-secret")
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    token = create_access_token("u001", settings, extra={"tenant_id": "default", "roles": ["customer"]})
    client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
    session = client.get("/api/v1/session?workspace=customer")
    assert session.status_code == 200
    assert session.json()["development_mode"] is False
    assert client.get("/api/v1/session?workspace=operations").status_code == 403
    assert client.get("/ops/api/runs?tenant_id=default").status_code == 403
    assert client.post("/api/v1/human-support/any/messages", json={
        "tenant_id": "default", "agent_id": "agent-001", "content": "injected"}).status_code == 403


def test_production_without_authentication_fails_closed():
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(runtime_env="production", security_enabled=False)
    assert TestClient(app).get("/api/v1/session").status_code == 401


def test_stream_request_checks_tenant_and_user_before_starting_worker(customer_client):
    for tenant, user in [("other-tenant", "u001"), ("default", "other-user")]:
        response = customer_client.post("/api/v1/chat/stream", json={
            "tenant_id": tenant, "user_id": user, "question": "test"})
        assert response.status_code == 403
