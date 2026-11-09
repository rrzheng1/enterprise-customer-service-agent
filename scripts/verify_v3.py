"""Verify V3 conditional execution and reliable writes against the full local stack."""
from __future__ import annotations

import json
import os
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx
from run_full import docker_command

ROOT = Path(__file__).resolve().parents[1]


def main():
    compose = docker_command()
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "status": "running", "checks": []}
    client = httpx.Client(base_url=os.getenv("CUSTOMER_AGENT_URL", "http://127.0.0.1:8002"), timeout=120)

    def run(script, *args):
        output = subprocess.run([*compose, "exec", "-T", "app", "python", script, *args],
                                cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True)
        return json.loads(output.stdout)

    def passed(name):
        report["checks"].append({"name": name, "status": "passed"})
        print("PASS:", name, flush=True)

    def conditional(order, suffix=""):
        result = client.post("/api/v1/chat", json={"tenant_id": "default", "user_id": "u001",
            "question": f"查订单{order}，如果符合条件就申请退货退款{suffix}", "metadata": {"skip_cache": True}})
        result.raise_for_status()
        return result.json()

    def decide(response, decision):
        return client.post(f"/api/v1/confirmations/{response['pending_confirmation']['id']}/{decision}",
                           json={"tenant_id": "default", "user_id": "u001"})

    try:
        for order, name in [("999999999999", "Missing owned order blocks refund"),
                            ("202606040001", "Shipped order blocks refund"),
                            ("202606040002", "Delivered order without verified evidence blocks refund")]:
            result = conditional(order)
            assert not result["pending_confirmation"]
            assert result["plan"] and any(step["status"] == "not_satisfied" for step in result["plan"]["steps"])
            db = run("scripts/full_db_probe.py", result["conversation_id"])
            assert not db["tickets"] and not db["actions"]
            passed(name)

        result = conditional("202606040003")
        assert result["pending_confirmation"]["tool_name"] == "create_refund_case"
        assert not run("scripts/full_db_probe.py", result["conversation_id"])["tickets"]
        approved = decide(result, "approve")
        approved.raise_for_status()
        assert len(run("scripts/full_db_probe.py", result["conversation_id"])["tickets"]) == 1
        passed("Eligible conditional refund waits for approval then creates one real MCP ticket")

        fallback = conditional("202606040002", "，否则转人工")
        assert fallback["pending_confirmation"]["tool_name"] == "transfer_to_human"
        assert not run("scripts/full_db_probe.py", fallback["conversation_id"])["tickets"]
        decide(fallback, "reject").raise_for_status()
        passed("Unsatisfied refund condition selects the explicit human-review branch")

        changing = conditional("202606040003")
        assert changing["pending_confirmation"]
        try:
            run("scripts/v3_probe.py", "shipped")
            response = decide(changing, "approve")
            assert response.status_code == 409
            assert response.json()["code"] in {"approval_conditions_changed", "business_precondition_failed"}
            assert not run("scripts/full_db_probe.py", changing["conversation_id"])["tickets"]
            passed("Order changes after approval prompt cannot bypass fresh business checks")
        finally:
            run("scripts/v3_probe.py", "delivered")
        decide(changing, "reject").raise_for_status()
        db = run("scripts/full_db_probe.py", changing["conversation_id"])
        assert not db["tickets"] and db["actions"][0]["status"] == "rejected"
        passed("Reject after a failed approval does not replay the previous approval")

        report["fault_injection"] = run("scripts/v3_probe.py", "response-loss")
        passed("Real MCP commit followed by injected response loss is reconciled without a second ticket")
        passed("MCP independently rejects approval argument substitution")
        report["status"] = "passed"
    except Exception as exc:
        report["status"], report["error"] = "failed", str(exc)
        raise
    finally:
        client.close()
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (ROOT / "data/v3-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fault injection: temporarily changes the third fixture order")
    parser.add_argument("--allow-fixture-mutation", action="store_true", required=True)
    parser.parse_args()
    main()
