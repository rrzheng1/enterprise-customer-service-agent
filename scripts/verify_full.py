"""Real LLM + RAG + MySQL + Redis + PostgreSQL + HTTP MCP acceptance checks.

Runs against docker-compose.full.yml only, creates demonstration refund tickets,
and restarts its app container to prove checkpoint persistence.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from run_full import docker_command

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    compose: list[str] = []
    report = {"started_at": datetime.now(timezone.utc).isoformat(),
              "base_url": os.getenv("CUSTOMER_AGENT_URL", "http://127.0.0.1:8002"), "status": "running", "checks": [], "artifacts": {}}
    client = httpx.Client(base_url=report["base_url"], timeout=120)

    def passed(name: str) -> None:
        report["checks"].append({"name": name, "status": "passed"})
        print("PASS:", name, flush=True)

    def api(method: str, path: str, **kwargs) -> dict:
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def chat(question: str, **fields) -> dict:
        return api("POST", "/api/v1/chat", json={
            "tenant_id": "default", "user_id": "u001", "question": question,
            "metadata": {"skip_cache": True, "validation_run": True}, **fields,
        })

    def probe(cid: str, expire: str | None = None) -> dict:
        command = [*compose, "exec", "-T", "app", "python", "scripts/full_db_probe.py", cid]
        if expire:
            command += ["--expire", expire]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def pending_refund() -> dict:
        response = chat("请为订单202606040003创建退款申请工单，原因是商品出现故障，请执行申请工具。")
        pending = response.get("pending_confirmation")
        assert pending and pending["tool_name"] == "create_refund_case", "Refund did not reach confirmation"
        return response

    def decision(response: dict, value: str) -> httpx.Response:
        action = response["pending_confirmation"]["id"]
        return client.post(f"/api/v1/confirmations/{action}/{value}", json={
            "tenant_id": "default", "user_id": "u001",
        })

    try:
        compose = docker_command()
        ready = api("GET", "/health/ready")
        assert ready["status"] == "ok"
        runtime = api("GET", "/ops/api/runtime")
        assert runtime["rag_enabled"] and runtime["mcp_after_sales_enabled"]
        passed("Full-stack readiness and RAG/MCP configuration")

        subprocess.run([*compose, "exec", "-T", "redis", "redis-cli", "ping"], check=True)
        passed("Real Redis connectivity; conversation lock enabled by full configuration")

        policy = chat("银行卡退款一般几天到账？")
        assert policy["knowledge"], "No retrieved knowledge"
        assert any(chunk["source"] == "faq/退款到账常见问题.md" for chunk in policy["knowledge"])
        assert policy["retrieval_quality"]["sufficient"]
        report["artifacts"]["policy_sources"] = sorted({chunk["source"] for chunk in policy["knowledge"]})
        report["artifacts"]["retrieval_quality"] = policy["retrieval_quality"]
        passed("RAG returns the expected refund policy source")

        order = chat("帮我查询订单202606040001的订单状态和物流单号")
        assert "SF1234567890" in order["answer"]
        followup = chat("是哪家快递公司？", conversation_id=order["conversation_id"])
        assert followup["conversation_id"] == order["conversation_id"] and "顺丰" in followup["answer"]
        passed("MCP order lookup and multi-turn context")

        for identity in [{"user_id": "u002"}, {"tenant_id": "another-tenant"}]:
            isolated = chat("帮我查询订单202606040001的物流单号", **identity)
            assert "SF1234567890" not in isolated["answer"]
            assert not any(item.get("payload", {}).get("found") for item in isolated["tool_results"])
        passed("MCP business ownership isolation across users and tenants")

        planned = chat("请分别查询订单202606040001的订单状态和物流状态，然后汇总这两项结果。")
        assert planned.get("plan"), "No structured plan generated"
        steps = planned["plan"]["steps"]
        tools = {step.get("tool_name") for step in steps}
        assert {"query_order_status", "query_logistics_status"}.issubset(tools)
        assert all(step["status"] == "success" for step in steps)
        passed("Planner executes both order and logistics steps")

        refund = pending_refund()
        cid = refund["conversation_id"]
        report["artifacts"].update({"refund_conversation_id": cid, "refund_thread_id": refund["thread_id"],
                                     "refund_confirmation_id": refund["pending_confirmation"]["id"],
                                     "refund_run_id": refund["run_id"]})
        before = probe(cid)
        assert not before["tickets"] and before["actions"][0]["status"] == "pending"
        state = api("GET", "/api/v1/graph/threads/" + refund["thread_id"])
        assert state["next_nodes"], "Checkpoint is not paused"
        passed("Pending action and PostgreSQL pause; no ticket before approval")

        subprocess.run([*compose, "restart", "app"], cwd=ROOT, check=True)
        deadline = time.monotonic() + 120
        while True:
            try:
                if api("GET", "/health/ready")["status"] == "ok":
                    break
            except (httpx.HTTPError, ValueError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("App did not recover after restart")
            time.sleep(1)
        restored = api("GET", "/api/v1/graph/threads/" + refund["thread_id"])
        assert restored["next_nodes"] == state["next_nodes"]
        approved = decision(refund, "approve")
        approved.raise_for_status()
        after = probe(cid)
        assert len(after["tickets"]) == 1 and after["actions"][0]["status"] == "executed"
        assert after["tickets"][0]["idempotency_key"], "MCP did not set ticket idempotency key"
        report["artifacts"]["refund_ticket_id"] = after["tickets"][0]["id"]
        passed("Process restart resumes same PostgreSQL checkpoint; real MCP creates one ticket")

        duplicate = decision(refund, "approve")
        assert duplicate.status_code in {200, 409}, "Unexpected duplicate approval response"
        assert probe(cid)["tickets"] == after["tickets"]
        passed("Duplicate approval does not create another ticket")

        rejected = pending_refund()
        reject_response = decision(rejected, "reject")
        reject_response.raise_for_status()
        rejected_db = probe(rejected["conversation_id"])
        assert not rejected_db["tickets"] and rejected_db["actions"][0]["status"] == "rejected"
        passed("Rejected refund leaves no business ticket")

        expired = pending_refund()
        probe(expired["conversation_id"], expired["pending_confirmation"]["id"])
        expiry_response = decision(expired, "approve")
        assert expiry_response.status_code in {400, 409, 410}, "Expired action was not refused"
        assert not probe(expired["conversation_id"])["tickets"]
        passed("Expired approval is rejected without side effects")

        run = api("GET", "/api/v1/agent-runs/" + refund["run_id"])
        assert run["steps"]
        passed("Agent run persists execution audit steps")
        report["status"] = "passed"
    except (Exception, SystemExit) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        raise
    finally:
        client.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        directory = ROOT / "data"
        directory.mkdir(exist_ok=True)
        (directory / "full-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
