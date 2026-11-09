"""Run official Gitleaks and inspect saved image layers; only redacted summaries leave memory."""
import argparse
import json
import re
import subprocess
import tarfile
from pathlib import Path
from dotenv import dotenv_values
from run_full import ROOT, docker_command


def secrets(paths):
    result = set()
    for path in paths:
        for key, value in dotenv_values(path).items():
            if value and len(value) >= 16 and re.search("KEY|TOKEN|SECRET|PASSWORD", key):
                result.add(value.encode())
    return result


def scan_image(engine, image, private):
    process = subprocess.Popen([*engine, "image", "save", image], stdout=subprocess.PIPE)
    findings = []
    layers = 0
    max_tail = max([len(s) for s in private] + [1])
    def inspect(stream):
        tail = b""
        while chunk := stream.read(1024 * 1024):
            block = tail + chunk
            if any(secret in block for secret in private):
                findings.append({"rule": "local-credential-in-image", "image": image})
                return
            tail = block[-max_tail:]
    with tarfile.open(fileobj=process.stdout, mode="r|*") as outer:
        for member in outer:
            if not member.isfile():
                continue
            stream = outer.extractfile(member)
            if member.name.endswith(".json") or member.size < 1024:
                inspect(stream)
                continue
            try:
                with tarfile.open(fileobj=stream, mode="r|*") as layer:
                    layers += 1
                    for item in layer:
                        name = item.name.lstrip("./")
                        if name in {"app/.env", "app/.env.full", "app/.env.release"} or name.startswith("app/data/"):
                            findings.append({"rule": "private-artifact-in-image", "image": image, "path": name})
                        if item.isfile():
                            inspect(layer.extractfile(item))
            except tarfile.ReadError:
                pass  # Manifest/config blobs are not filesystem layers.
    assert process.wait() == 0, "docker image save failed"
    return {"image": image, "filesystem_layers_checked": layers, "findings": findings}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--images", nargs="*", default=[])
    parser.add_argument("--private-env", type=Path, action="append", default=[])
    args = parser.parse_args()
    prefix = docker_command()
    engine = prefix[:prefix.index("compose")]
    result = subprocess.run([*engine, "run", "--rm", "-v", f"{args.context.resolve()}:/repo:ro",
        "-v", f"{ROOT / '.gitleaks.toml'}:/scanner.toml:ro", "ghcr.io/gitleaks/gitleaks:v8.30.1",
        "dir", "/repo", "--config", "/scanner.toml", "--redact=100", "--no-banner",
        "--report-format", "json", "--report-path", "-"], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode in {0, 1}, "Scanner failed to execute; no secret output will be printed"
    parsed = json.loads(result.stdout or "[]")
    report = {"scanner": "gitleaks 8.30.1", "source_findings": [
        {"path": f.get("File"), "line": f.get("StartLine"), "rule": f.get("RuleID"), "secret": "[REDACTED]"}
        for f in parsed], "git_history": "not-available-without-git", "images": []}
    private = secrets([ROOT / ".env", ROOT / ".env.full", *args.private_env])
    for image in args.images:
        report["images"].append(scan_image(engine, image, private))
    report["status"] = "passed" if not parsed and not any(i["findings"] for i in report["images"]) else "findings"
    destination = ROOT / "data/release/security-scan.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
