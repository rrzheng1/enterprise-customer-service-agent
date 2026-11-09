"""Create an isolated full-stack environment without modifying the local .env."""
from __future__ import annotations

import os
import secrets
import time
import argparse
from pathlib import Path

from dotenv import dotenv_values
from jose import jwt

ROOT = Path(__file__).resolve().parents[1]


def prepare(path: Path | None = None, source_env: Path | None = None, overrides: dict | None = None) -> Path:
    path = path or ROOT / ".env.full"
    values = {key: value for key, value in dotenv_values(path).items() if value}
    local = dotenv_values(source_env or ROOT / ".env")
    defaults = {
        "RUNTIME_ENV": "local", "SECURITY_ENABLED": "false",
        "LLM_PROVIDER": "openai_compatible", "LLM_MODEL": local.get("LLM_MODEL") or "qwen3.7-plus",
        "LLM_BASE_URL": local.get("LLM_BASE_URL", ""),
        "LLM_API_KEY": local.get("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY", ""),
        "EMBEDDING_PROVIDER": local.get("EMBEDDING_PROVIDER") or "dashscope",
        "EMBEDDING_BASE_URL": local.get("EMBEDDING_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "EMBEDDING_MODEL": local.get("EMBEDDING_MODEL") or "text-embedding-v4",
        "EMBEDDING_DIMENSION": local.get("EMBEDDING_DIMENSION") or "1024",
        "KNOWLEDGE_INGEST_BATCH_SIZE": "10", "RAG_ENABLED": "true",
        "VECTOR_STORE_PROVIDER": "qdrant", "QDRANT_URL": "http://qdrant:6333",
        "RETRIEVAL_MODE": "dense", "OPENSEARCH_ENABLED": "false", "RERANK_ENABLED": "false",
        "REDIS_URL": "redis://redis:6379/0", "SEMANTIC_CACHE_ENABLED": "false",
        "REQUEST_LOCK_ENABLED": "true", "GRAPH_CHECKPOINTER": "postgres",
        "V2_HIL_ENABLED": "true", "GRAPH_DURABILITY": "sync",
        "MCP_AFTER_SALES_ENABLED": "true", "MCP_AFTER_SALES_TRANSPORT": "streamable_http",
        "MCP_AFTER_SALES_URL": "http://after-sales-mcp:8100/mcp",
        "MCP_SERVICE_AUTH_ENABLED": "true", "MCP_SERVICE_AUTH_ISSUER": "customer-service-agent",
        "MCP_SERVICE_AUTH_AUDIENCE": "http://after-sales-mcp:8100",
        "LANGSMITH_TRACING": "false", "OTEL_ENABLED": "false",
    }
    for key, value in defaults.items():
        values.setdefault(key, value)
    for key in ["FULL_MYSQL_PASSWORD", "FULL_MYSQL_ROOT_PASSWORD", "FULL_POSTGRES_PASSWORD",
                "MCP_APPROVAL_SIGNING_SECRET", "MCP_SERVICE_AUTH_SECRET", "MCP_CALL_SIGNING_SECRET"]:
        values.setdefault(key, secrets.token_hex(24))
    values.setdefault("EMBEDDING_API_KEY", local.get("EMBEDDING_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or values["LLM_API_KEY"])
    values.update(overrides or {})
    values.setdefault("DATABASE_URL", "mysql+aiomysql://customer_service:"
                      + values["FULL_MYSQL_PASSWORD"] + "@mysql:3306/customer_service?charset=utf8mb4")
    values.setdefault("GRAPH_CHECKPOINT_POSTGRES_URL", "postgresql://graph:"
                      + values["FULL_POSTGRES_PASSWORD"] + "@checkpoint-postgres:5432/graph_checkpoint")
    if not all(values.get(key) for key in ["LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"]):
        raise SystemExit("Configure LLM_API_KEY, LLM_BASE_URL and LLM_MODEL in .env first.")
    # Renew the short-lived service credential on every start; keep signing keys and DB passwords.
    now = int(time.time())
    values["MCP_SERVICE_AUTH_TOKEN"] = jwt.encode({
        "sub": "local-customer-agent", "iss": values["MCP_SERVICE_AUTH_ISSUER"],
        "aud": values["MCP_SERVICE_AUTH_AUDIENCE"], "scope": "mcp:invoke",
        "iat": now, "exp": now + 24 * 60 * 60,
    }, values["MCP_SERVICE_AUTH_SECRET"], algorithm="HS256")
    for value in values.values():
        if any(char in value for char in "\r\n'"):
            raise SystemExit("Environment values must be single-line and contain no single quote.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Generated local full stack; contains secrets. Do not commit.\n"
                    + "".join(f"{key}='{value}'\n" for key, value in values.items()), encoding="utf-8")
    print("Full-stack configuration prepared. Secret values are hidden; .env is unchanged.")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-env", type=Path)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    prepare(args.output, args.source_env, {"FULL_HTTP_PORT": str(args.port)} if args.port else None)
