"""Exercise real HTTP MCP auth and signed read calls using the local demo database.

This is a transport smoke test, not the MySQL/PostgreSQL full-stack acceptance test.
"""
from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from customer_service_app.infrastructure.mcp.client import StreamableHttpMCPBusinessClient  # noqa: E402


async def check(port: int, config: dict) -> None:
    client = StreamableHttpMCPBusinessClient(
        url=f"http://127.0.0.1:{port}/mcp", timeout_seconds=20,
        service_auth_token=config["MCP_SERVICE_AUTH_TOKEN"],
        call_signing_secret=config["MCP_CALL_SIGNING_SECRET"],
        call_context_ttl_seconds=60, contract_cache_ttl_seconds=300,
    )
    try:
        await client.start()
        tools = await client.list_tools()
        assert any(tool.name == "query_order_status" for tool in tools)
        for user_id, found in [("u001", True), ("u002", False)]:
            result = await client.call_tool(name="query_order_status", arguments={
                "tenant_id": "default", "user_id": user_id, "order_id": "202606040001",
            })
            assert result["found"] is found
        print("PASS: HTTP MCP discovery, service JWT, signed context, owned query and isolation")
    finally:
        await client.close()


def main() -> None:
    config = dotenv_values(ROOT / ".env.full")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": "sqlite+aiosqlite:///" + (ROOT / "data/demo.db").as_posix(),
        "HOST": "127.0.0.1", "PORT": str(port),
        "APPROVAL_SIGNING_SECRET": config["MCP_APPROVAL_SIGNING_SECRET"],
        "SERVICE_AUTH_ENABLED": "true", "SERVICE_AUTH_SECRET": config["MCP_SERVICE_AUTH_SECRET"],
        "SERVICE_AUTH_ISSUER": "customer-service-agent",
        "SERVICE_AUTH_AUDIENCE": config["MCP_SERVICE_AUTH_AUDIENCE"],
        "SERVICE_AUTH_RESOURCE_URL": f"http://127.0.0.1:{port}",
        "CALL_SIGNING_SECRET": config["MCP_CALL_SIGNING_SECRET"],
    })
    with (ROOT / "data/mcp-smoke.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, "scripts/run_after_sales_mcp_server.py"],
                                   cwd=ROOT, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 20
            while True:
                if process.poll() is not None:
                    raise RuntimeError("MCP exited; inspect data/mcp-smoke.log")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("MCP did not start within 20 seconds")
                    time.sleep(0.2)
            asyncio.run(check(port, config))
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
