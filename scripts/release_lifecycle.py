"""Restart only the independent rehearsal app; verify checkpoints, volumes and immutable fixtures."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path
import httpx
from run_full import ROOT, docker_command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--project", default="customer-agent-release-p5")
    parser.add_argument("--port", type=int, default=18002)
    args = parser.parse_args()
    context = args.context.resolve()
    target = (args.env_file or context / ".env.release").resolve()
    assert args.project.startswith("customer-agent-release-") and args.port != 8002
    prefix = docker_command(target, args.project)
    prefix[prefix.index("-f") + 1] = str(context / "docker-compose.full.yml")
    env = dict(os.environ, CUSTOMER_AGENT_ENV_FILE=str(target))
    report = {"status": "running", "checks": []}
    def run(*arguments):
        result = subprocess.run([*prefix, *arguments], env=env, cwd=context, capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            raise RuntimeError("Isolated lifecycle Compose command failed (credential-bearing output withheld)")
        return result.stdout
    def facts():
        code = """import asyncio,json,hashlib
from sqlalchemy import select,func
from customer_service_app.infrastructure.db.models import Order,SupportTicket
from customer_service_app.infrastructure.db.session import session_context,dispose_engine
async def read():
 async with session_context() as s:
  rows=(await s.execute(select(Order).where(Order.tenant_id=='default',Order.user_id=='u001'))).scalars().all()
  orders=[{'id':o.order_id,'status':o.status,'metadata_hash':hashlib.sha256(json.dumps(o.metadata_json,sort_keys=True).encode()).hexdigest()} for o in rows]
  tickets=(await s.execute(select(func.count()).select_from(SupportTicket))).scalar_one()
 await dispose_engine()
 return {'orders':sorted(orders,key=lambda x:x['id']),'tickets':tickets}
print(json.dumps(asyncio.run(read())))"""
        return json.loads(run("exec", "-T", "app", "python", "-c", code))
    def passed(name):
        report["checks"].append(name)
        print("PASS:", name, flush=True)
    try:
        run("up", "-d", "--no-build", "--no-deps", "--force-recreate", "--wait", "--wait-timeout", "180", "app")
        client = httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=120)
        before = facts()
        assert [o["status"] for o in before["orders"]] == ["shipped", "delivered", "delivered"]
        response = client.post("/api/v1/chat", json={"tenant_id": "default", "user_id": "u001",
            "question": "查订单202606040003，如果符合条件就申请退货退款"})
        response.raise_for_status()
        pending = response.json()
        assert pending["pending_confirmation"] and pending["thread_id"]
        run("stop", "app")
        run("start", "app")
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                if client.get("/health/ready").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Restart did not become ready")
        graph = client.get(f"/api/v1/graph/threads/{pending['thread_id']}")
        graph.raise_for_status()
        assert "await_confirmation" in graph.json()["next_nodes"]
        action = pending["pending_confirmation"]["id"]
        owned = {"tenant_id": "default", "user_id": "u001"}
        assert client.get(f"/api/v1/confirmations/{action}", params=owned).json()["status"] == "pending"
        passed("PostgreSQL checkpoint and pending approval survive application stop/start")
        rejection = client.post(f"/api/v1/confirmations/{action}/reject", json=owned)
        rejection.raise_for_status()
        assert rejection.json()["status"] == "rejected"
        after = facts()
        report["before"] = before
        report["after"] = after
        assert before == after
        report["fixture_facts_unchanged"] = True
        passed("Order statuses, complete pre-review metadata and existing demo ticket count unchanged after restart/rejection")
        engine = prefix[:prefix.index("compose")]
        volumes = subprocess.check_output([*engine, "volume", "ls", "--filter", f"label=com.docker.compose.project={args.project}", "--format", "{{.Name}}"], text=True).splitlines()
        assert len(volumes) == 4
        report["volumes"] = volumes
        passed("Four dedicated named volumes persist; no volume removal or development-stack command issued")
        report["status"] = "passed"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = type(exc).__name__
        raise
    finally:
        (ROOT / "data/release/lifecycle.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
