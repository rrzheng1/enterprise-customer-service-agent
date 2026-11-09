"""Run offline CI-equivalent checks against a clean read-only checkout and built dependencies."""
import argparse
import subprocess
from run_full import ROOT, docker_command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    prefix = docker_command()
    engine = prefix[:prefix.index("compose")]
    from pathlib import Path
    source = Path(args.source).resolve()
    commands = [["python", "-m", "pip", "check"], ["python", "scripts/check_dependencies.py"],
        ["python", "-m", "pytest", "-q", "-c", "pyproject.toml"],
        ["ruff", "check", "--no-cache", "--select", "E4,E7,E9,F", "src", "tests", "scripts", "mcp_services/after_sales_server/src"],
        ["python", "scripts/check_openapi.py"]]
    for command in commands:
        result = subprocess.run([*engine, "run", "--rm", "-w", "/workspace",
            "-v", f"{source}:/workspace:ro", "-e", "PYTHONPATH=/workspace/src:/workspace/mcp_services/after_sales_server/src",
            "-e", "RUNTIME_ENV=test", "-e", "DATABASE_URL=sqlite+aiosqlite:////tmp/customer-agent-ci.db",
            "-e", "GRAPH_CHECKPOINTER=memory", "-e", "V2_HIL_ENABLED=false", "-e", "SEMANTIC_CACHE_ENABLED=false",
            "-e", "REQUEST_LOCK_ENABLED=false", "-e", "PYTEST_ADDOPTS=-p no:cacheprovider", "customer-agent:p5", *command],
            capture_output=True, encoding="utf-8", errors="replace")
        with (ROOT / "data/release/linux-ci.log").open("a", encoding="utf-8") as log:
            log.write(result.stdout + result.stderr)
        print(result.stdout[-1800:], flush=True)
        if result.returncode:
            raise SystemExit(f"Linux check failed: {command[0:3]} (see private log)")


if __name__ == "__main__":
    main()
