"""Build real images from an exported context. Does not touch existing services or volumes."""
import argparse
import subprocess
from pathlib import Path
from run_full import ROOT, docker_command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--tag", default="customer-agent:p5")
    parser.add_argument("--mcp-tag", default="customer-agent-mcp:p5")
    args = parser.parse_args()
    compose = docker_command()
    engine = compose[:compose.index("compose")]
    log_path = ROOT / "data/release/build-images.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    def run(*arguments):
        result = subprocess.run([*engine, *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit("Image build failed; inspect data/release/build-images.log")
    for image in ["python:3.11-slim", "node:24-alpine"]:
        found = subprocess.run([*engine, "image", "inspect", image], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if found.returncode:
            run("pull", image)
    run("build", "--progress=plain", "-t", args.tag, str(args.context.resolve()))
    run("build", "--progress=plain", "-f", "mcp_services/after_sales_server/Dockerfile", "-t", args.mcp_tag, str(args.context.resolve()))
    print("Both images built from the exported source context; no running container was synced.")


if __name__ == "__main__":
    main()
