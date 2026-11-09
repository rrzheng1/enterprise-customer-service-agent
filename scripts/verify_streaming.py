"""Real HTTP/model/MCP acceptance; never modifies seeded order facts or re-POSTs on disconnect."""
import json
import os
import time
import uuid
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from customer_service_app.domain.streaming import StreamEvent  # noqa: E402

BASE = os.getenv("CUSTOMER_AGENT_URL", "http://127.0.0.1:8002")
OWN = {"tenant_id": "default", "user_id": "u001"}


def main():
    report = {"status": "running", "checks": [], "runs": []}
    client = httpx.Client(base_url=BASE, timeout=180)

    def passed(name):
        report["checks"].append(name)
        print("PASS:", name, flush=True)

    def workspace(cid):
        r = client.get(f"/api/v1/conversations/{cid}/workspace", params=OWN)
        r.raise_for_status()
        return r.json()

    def chat(question):
        started = time.perf_counter()
        events = []
        with client.stream("POST", "/api/v1/chat/stream", json={**OWN, "question": question,
                "metadata": {"idempotency_key": str(uuid.uuid4()), "skip_cache": True}}) as r:
            r.raise_for_status()
            assert r.headers["content-type"].startswith("text/event-stream")
            for line in r.iter_lines():
                if not line.startswith("data: "):
                    continue
                e = StreamEvent.model_validate_json(line[6:]).model_dump(mode="json")
                events.append({**e, "arrival_seconds": time.perf_counter() - started})
                if e["event_type"] in {"run_failed", "stream_interrupted"}:
                    raise AssertionError(e["payload"])
                if e["event_type"] == "run_completed":
                    break
        assert events and events[-1]["event_type"] == "run_completed"
        assert [e["sequence"] for e in events] == sorted(set(e["sequence"] for e in events))
        assert len({e["event_id"] for e in events}) == len(events)
        first_node = next(e for e in events if e["event_type"] == "node_completed")
        assert first_node["arrival_seconds"] < events[-1]["arrival_seconds"]
        report["runs"].append({"run_id": events[-1]["run_id"], "conversation_id": events[-1]["conversation_id"],
            "first_node_seconds": first_node["arrival_seconds"], "completed_seconds": events[-1]["arrival_seconds"],
            "event_types": [e["event_type"] for e in events],
            "delta_count": sum(e["event_type"] == "answer_delta" for e in events)})
        return events, workspace(events[-1]["conversation_id"])

    def decide(action, decision):
        r = client.post(f"/api/v1/confirmations/{action['id']}/{decision}", json=OWN)
        r.raise_for_status()
        return r.json()

    try:
        ready = client.get("/health/ready")
        ready.raise_for_status()
        assert ready.json()["status"] == "ok"
        events, w = chat("查询订单202606040001的物流进度")
        deltas = [e["payload"]["text"] for e in events if e["event_type"] == "answer_delta"]
        assert len(deltas) > 1, "No native final-answer deltas from the provider"
        assert "".join(deltas) == events[-1]["payload"]["answer"]
        assert w["messages"] and w["responses"]
        passed("Real node completion precedes terminal event; native model deltas equal the persisted answer")
        passed("Public event schemas, monotonic sequences and unique event IDs validated")
        for order in ["202606040001", "202606040002"]:
            _, w = chat(f"查订单{order}，如果符合条件就申请退货退款")
            assert not w["pending_actions"] and not w["tickets"]
            passed(f"{order} blocks refund without approval or ticket")
        _, w = chat("查订单202606040003，如果符合条件就申请退货退款")
        assert len(w["pending_actions"]) == 1 and not w["tickets"]
        action = w["pending_actions"][0]
        decide(action, "approve")
        approved = workspace(w["conversation"]["id"])
        assert len(approved["tickets"]) == 1
        ticket = approved["tickets"][0]["id"]
        # Duplicate approval must not create a second ticket; a conflict is acceptable.
        duplicate = client.post(f"/api/v1/confirmations/{action['id']}/approve", json=OWN)
        assert duplicate.status_code in {200, 409}
        assert [t["id"] for t in workspace(w["conversation"]["id"])["tickets"]] == [ticket]
        passed("PostgreSQL approval resume creates one real MCP ticket; duplicate approval preserves one ticket")
        _, w = chat("查订单202606040003，如果符合条件就申请退货退款")
        decide(w["pending_actions"][0], "reject")
        assert not workspace(w["conversation"]["id"])["tickets"]
        passed("Reject resumes the checkpoint without creating a ticket")
        # Disconnect as soon as a real node has completed. Only GET requests follow.
        cid = client.post("/api/v1/conversations", json={**OWN, "title": "SSE断线恢复验收"}).json()["id"]
        key = str(uuid.uuid4())
        with client.stream("POST", "/api/v1/chat/stream", json={**OWN, "conversation_id": cid,
                "question": "查询订单202606040001的物流进度", "metadata": {"idempotency_key": key}}) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line.startswith("data: ") and json.loads(line[6:])["event_type"] == "node_completed":
                    break
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            w = workspace(cid)
            run = next((r for r in w["runs"] if r["request_id"] == key), None)
            if run and run["status"] == "success":
                break
            time.sleep(1)
        else:
            raise AssertionError("Detached run did not persist a terminal result")
        assert len([r for r in w["runs"] if r["request_id"] == key]) == 1
        assert len([m for m in w["messages"] if m["role"] == "assistant"]) == 1
        passed("Closing HTTP connection leaves one worker/run that completes; GET-only recovery restores one answer")
        r = client.post("/api/v1/chat", json={**OWN, "question": "查询订单202606040001的状态"})
        r.raise_for_status()
        assert {"answer", "tool_results", "trace", "conversation_id", "thread_id"} <= r.json().keys()
        passed("Original non-streaming ChatResponse contract remains available")
        report["status"] = "passed"
    except Exception as exc:
        report["status"], report["error"] = "failed", str(exc)
        raise
    finally:
        client.close()
        (ROOT / "data/stream-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
