"""Exercise clean Node lockfile dependencies and an actual Vite proxy on the isolated network."""
import argparse
import json
import subprocess
import time
import sys
from pathlib import Path
import httpx
from run_full import ROOT, docker_command


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path, required=True)
    args = parser.parse_args()
    prefix = docker_command()
    engine = prefix[:prefix.index("compose")]
    def run(*arguments):
        result = subprocess.run([*engine, *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace")
        with (ROOT / "data/release/frontend-container-details.log").open("a", encoding="utf-8") as handle:
            handle.write(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit("Frontend container check failed; inspect the private details log")
        if "test" in arguments or "typecheck" in arguments:
            print(result.stdout[-1600:], flush=True)
    run("build", "--target", "frontend-build", "-t", "customer-agent-ui:p5", str(args.context.resolve()))
    run("run", "--rm", "customer-agent-ui:p5", "npm", "run", "typecheck")
    run("run", "--rm", "customer-agent-ui:p5", "npm", "test")
    # A separate container/port; do not touch the developer's Vite process or node_modules.
    existing = subprocess.run([*engine, "container", "inspect", "customer-agent-release-p5-vite"], capture_output=True)
    if existing.returncode:
        run("run", "-d", "--name", "customer-agent-release-p5-vite", "--network", "customer-agent-release-p5_default",
            "-p", "127.0.0.1:15173:5173", "-e", "BACKEND_URL=http://app:8000", "customer-agent-ui:p5",
            "npm", "run", "dev", "--", "--host", "0.0.0.0")
    else:
        run("start", "customer-agent-release-p5-vite")
    deadline = time.monotonic() + 60
    with httpx.Client(base_url="http://127.0.0.1:15173", timeout=5) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get("/ui/config")
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Isolated Vite proxy did not start")
        assert client.get("/chat").status_code == 200
        assert client.get("/api/v1/session").json()["development_mode"] is True
        assert client.get("/health/ready").json()["status"] == "ok"
    report = {"status": "passed", "checks": ["Clean npm ci dependencies in Node build stage", "Linux TypeScript and Vitest",
        "Real Vite proxy for config/session/health and frontend route"], "url": "http://127.0.0.1:15173"}
    (ROOT / "data/release/frontend-container.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS: clean Node checks and independent Vite proxy")


if __name__ == "__main__":
    main()
