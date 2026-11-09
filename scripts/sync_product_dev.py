"""Sync built UI and HTTP adapters into the dedicated local Docker app (no env changes).

Development only. Rebuild the Docker image for reproducible distribution.
"""
import subprocess
import time
import urllib.request
from run_full import ROOT, docker_command


def main():
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise SystemExit("Run npm ci and npm run build in frontend first")
    compose = docker_command()
    engine = compose[:compose.index("compose")]
    container = subprocess.check_output([*compose, "ps", "-q", "app"], text=True).strip()
    if not container:
        raise SystemExit("Start the dedicated full-stack app first")
    subprocess.run([*compose, "exec", "-T", "app", "mkdir", "-p", "/app/frontend/dist"], check=True)
    for source, target in [("src/customer_service_app/.", "/app/src/customer_service_app"),
                           ("frontend/dist/.", "/app/frontend/dist")]:
        subprocess.run([*engine, "cp", source, f"{container}:{target}"], cwd=ROOT, check=True)
    subprocess.run([*compose, "restart", "app"], check=True)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8002/health/ready", timeout=3) as response:
                if response.status == 200:
                    break
        except OSError:
            pass
        time.sleep(1)
    else:
        raise SystemExit("App did not become ready; inspect the dedicated container logs")
    print("Product UI synced to http://127.0.0.1:8002 (development container only)")


if __name__ == "__main__":
    main()
