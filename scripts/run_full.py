"""Build, migrate, ingest knowledge, and start the isolated Docker full stack."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from prepare_full import prepare

ROOT = Path(__file__).resolve().parents[1]


def docker_command(env_file: Path | None = None, project: str | None = None) -> list[str]:
    docker = shutil.which("docker")
    candidates = [Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe"),
                  Path(os.getenv("LOCALAPPDATA", "")) / "Programs/DockerDesktop/resources/bin/docker.exe"]
    if not docker:
        docker = next((str(path) for path in candidates if path.is_file()), None)
    if not docker:
        raise SystemExit("Docker Desktop is required. Install/start it, then retry start-full.cmd.")
    # New Desktop installs may not be on this terminal's PATH yet. Helpers inherit this
    # process-local PATH; no user or system environment setting is changed.
    os.environ["PATH"] = str(Path(docker).parent) + os.pathsep + os.environ.get("PATH", "")
    engine = [docker]
    if os.name == "nt" and not os.getenv("DOCKER_HOST"):
        engine += ["--host", "npipe:////./pipe/dockerDesktopLinuxEngine"]
    result = subprocess.run([*engine, "info"], capture_output=True, timeout=30)
    if result.returncode:
        raise SystemExit("Docker engine is not ready. Start Docker Desktop and wait for the engine.")
    selected = (env_file or Path(os.getenv("CUSTOMER_AGENT_ENV_FILE", str(ROOT / ".env.full")))).resolve()
    os.environ["CUSTOMER_AGENT_ENV_FILE"] = str(selected)
    command = [*engine, "compose", "--env-file", str(selected), "-f", str(ROOT / "docker-compose.full.yml")]
    project = project or os.getenv("CUSTOMER_AGENT_PROJECT")
    if project:
        os.environ["CUSTOMER_AGENT_PROJECT"] = project
        command += ["--project-name", project]
    return command


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ingest", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--source-env", type=Path)
    parser.add_argument("--project")
    parser.add_argument("--port", type=int)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    selected_env = args.env_file or Path(os.getenv("CUSTOMER_AGENT_ENV_FILE", str(ROOT / ".env.full")))
    prepare(selected_env, args.source_env, {"FULL_HTTP_PORT": str(args.port)} if args.port else None)
    compose = docker_command(selected_env, args.project)

    def run(*arguments: str) -> None:
        subprocess.run([*compose, *arguments], cwd=ROOT, check=True)

    run("config", "--quiet")  # Never print resolved secrets.
    run("up", "-d", "--wait", "--wait-timeout", "300", "mysql", "redis", "qdrant", "checkpoint-postgres")
    engine = compose[:compose.index("compose")]
    base_image = subprocess.run([*engine, "image", "inspect", "python:3.11-slim"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if base_image.returncode:
        subprocess.run([*engine, "pull", "python:3.11-slim"], check=True)
    if not args.skip_build:
        run("build", "app", "after-sales-mcp")
    run("run", "--rm", "--no-deps", "init")
    if not args.skip_ingest:
        run("run", "--rm", "--no-deps", "app", "python", "scripts/ingest_docs.py", "knowledge_base", "--tenant-id", "default")
    # Recreate app so a renewed service JWT is actually loaded.
    run("up", "-d", "--force-recreate", "--wait", "--wait-timeout", "300", "app")
    from dotenv import dotenv_values
    port = dotenv_values(selected_env).get("FULL_HTTP_PORT") or "8002"
    print(f"Full-stack console: http://127.0.0.1:{port}/")
    if args.verify:
        os.environ["CUSTOMER_AGENT_URL"] = f"http://127.0.0.1:{port}"
        subprocess.run([sys.executable, "scripts/verify_full.py"], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
