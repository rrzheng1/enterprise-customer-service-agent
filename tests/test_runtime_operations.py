from __future__ import annotations

import uuid
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from customer_service_app.api import routes_health
from customer_service_app.core.config import Settings
from customer_service_app.core.middleware import RequestContextMiddleware


def test_full_environment_preserves_local_settings_and_database_credentials(tmp_path, monkeypatch, capsys):
    from dotenv import dotenv_values

    spec = importlib.util.spec_from_file_location(
        "prepare_full_test", Path(__file__).resolve().parents[1] / "scripts" / "prepare_full.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    local = "LLM_API_KEY=private-test-key\nLLM_BASE_URL=https://example.test/v1\nLLM_MODEL=selected-chat-model\n"
    (tmp_path / ".env").write_text(local, encoding="utf-8")
    monkeypatch.setattr(module.time, "time", lambda: 1000)
    module.prepare()
    first = dotenv_values(tmp_path / ".env.full")
    monkeypatch.setattr(module.time, "time", lambda: 1100)
    module.prepare()
    second = dotenv_values(tmp_path / ".env.full")
    assert (tmp_path / ".env").read_text(encoding="utf-8") == local
    assert first["DATABASE_URL"] == second["DATABASE_URL"]
    assert first["LLM_MODEL"] == "selected-chat-model"
    assert first["MCP_CALL_SIGNING_SECRET"] == second["MCP_CALL_SIGNING_SECRET"]
    assert first["MCP_SERVICE_AUTH_TOKEN"] != second["MCP_SERVICE_AUTH_TOKEN"]
    assert "private-test-key" not in capsys.readouterr().out


def _middleware_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/items/{item_id}")
    async def read_item(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    return app


def test_request_context_preserves_valid_request_id() -> None:
    client = TestClient(_middleware_test_app())

    response = client.get("/items/1", headers={"x-request-id": "gateway-req-001"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "gateway-req-001"


def test_request_context_replaces_untrusted_request_id() -> None:
    client = TestClient(_middleware_test_app())

    response = client.get("/items/1", headers={"x-request-id": "invalid request\nvalue"})

    assert response.status_code == 200
    generated = response.headers["x-request-id"]
    assert uuid.UUID(generated)


@pytest.mark.asyncio
async def test_readiness_accepts_milvus_vector_store(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        rag_enabled=True,
        llm_api_key="secret",
        llm_base_url="https://llm.example.com/v1",
        llm_model="chat-model",
        database_url="mysql+aiomysql://user:secret@mysql/database",
        embedding_base_url="https://embedding.example.com/v1",
        embedding_model="embedding-model",
        vector_store_provider="milvus",
        milvus_uri="https://milvus.example.com",
        graph_checkpointer="memory",
        v2_hil_enabled=False,
    )
    monkeypatch.setattr(routes_health, "get_settings", lambda: settings)

    response = await routes_health.ready()

    assert response["status"] == "ok"
    assert response["checks"]["rag_configured"] is True


@pytest.mark.asyncio
async def test_readiness_rejects_incomplete_security_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        llm_api_key="secret",
        llm_base_url="https://llm.example.com/v1",
        llm_model="chat-model",
        database_url="mysql+aiomysql://user:secret@mysql/database",
        embedding_base_url="https://embedding.example.com/v1",
        embedding_model="embedding-model",
        qdrant_url="https://qdrant.example.com",
        security_enabled=True,
        jwt_secret_key="secret",
        jwt_issuer="",
        jwt_audience="customer-service",
    )
    monkeypatch.setattr(routes_health, "get_settings", lambda: settings)

    response = await routes_health.ready()

    assert response["status"] == "not_ready"
    assert response["checks"]["security_configured"] is False
