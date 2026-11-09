"""Initialize an isolated full stack from built images, never the developer's project/volumes."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path
import httpx
from dotenv import dotenv_values
from prepare_full import prepare
from run_full import ROOT, docker_command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--project", default="customer-agent-release-p5")
    parser.add_argument("--port", type=int, default=18002)
    parser.add_argument("--source-env", type=Path, default=ROOT / ".env.full")
    args = parser.parse_args()
    assert args.project != "customer-agent-full", "Refusing to use the development project"
    assert args.port != 8002, "Choose a separate rehearsal port"
    context = args.context.resolve()
    target = context / ".env.release"
    prepare(target, args.source_env, {"FULL_HTTP_PORT": str(args.port),
        "CUSTOMER_AGENT_IMAGE": "customer-agent:p5", "CUSTOMER_AGENT_MCP_IMAGE": "customer-agent-mcp:p5"})
    prefix = docker_command(target, args.project)
    # The compose definition must also come from the exported source copy.
    prefix[prefix.index("-f") + 1] = str(context / "docker-compose.full.yml")
    env = dict(os.environ, CUSTOMER_AGENT_ENV_FILE=str(target))
    values = dotenv_values(target)
    secret_values = [v for k, v in values.items() if v and re.search("KEY|TOKEN|SECRET|PASSWORD", k)]
    report = {"project": args.project, "port": args.port, "checks": [], "status": "running"}
    log = ROOT / "data/release/rehearsal.log"
    log.write_text("Isolated release rehearsal (redacted)\n", encoding="utf-8")

    def run(*arguments):
        result = subprocess.run([*prefix, *arguments], cwd=context, env=env,
                                capture_output=True, encoding="utf-8", errors="replace")
        text = result.stdout + result.stderr
        for secret in secret_values:
            text = text.replace(secret, "[REDACTED]")
        with log.open("a", encoding="utf-8") as handle:
            handle.write(text)
        if result.returncode:
            raise RuntimeError(f"Compose {arguments[0]} failed; inspect the redacted private rehearsal log")
        return result.stdout

    def passed(name):
        report["checks"].append(name)
        print("PASS:", name, flush=True)

    try:
        run("config", "--quiet")
        run("up", "--no-build", "-d", "--wait", "--wait-timeout", "300", "mysql", "redis", "qdrant", "checkpoint-postgres")
        passed("Independent database/cache/vector containers and project-scoped volumes started")
        run("up", "--no-build", "--no-deps", "--abort-on-container-exit", "--exit-code-from", "init", "init")
        passed("Fresh MySQL Alembic migrations and original seed script completed")
        run("run", "--rm", "--no-deps", "app", "python", "scripts/ingest_docs.py", "knowledge_base", "--tenant-id", "default")
        passed("Real configured embedding and clean Qdrant knowledge ingestion completed")
        run("up", "--no-build", "-d", "--wait", "--wait-timeout", "300", "app")
        passed("Built application and MCP images started; container health checks passed")
        with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=30) as client:
            r = client.get("/health/ready")
            assert r.status_code == 200 and r.json()["status"] == "ok"
            passed("HTTP readiness returned ok (not a substitute for business E2E)")
            for path in ["/chat", "/operations", "/demo", "/chat/reload-check", "/ops", "/demo/legacy"]:
                assert client.get(path).status_code == 200, f"Route failed: {path}"
            html = client.get("/chat").text
            assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
            assert assets
            for path in assets:
                response = client.get(path)
                assert response.status_code == 200 and "text/html" not in response.headers.get("content-type", "")
            assert client.get("/api/v1/session").json()["development_mode"] is True
            assert client.get("/ops/api/conversations", params={"tenant_id": "default"}).status_code == 200
            passed("Customer/operations/demo/legacy routes, deep refresh, static assets and same-origin API passed")
        report["status"] = "passed"
    except Exception as exc:
        report["status"], report["error"] = "failed", str(exc)
        raise
    finally:
        (ROOT / "data/release/rehearsal.json").write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
