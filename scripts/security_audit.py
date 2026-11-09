"""Redacted release audit: exact local credentials + tracked private paths. Never prints values."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values
from release_export import ROOT, public_files


def audit(require_git=False):
    secret_values = set()
    for source in [dotenv_values(ROOT / ".env"), dotenv_values(ROOT / ".env.full"), os.environ]:
        for key, value in source.items():
            if re.search(r"KEY|TOKEN|SECRET|PASSWORD", key) and value and len(value) >= 16:
                secret_values.add(value.encode())
    findings = []
    files = list(public_files())
    for path in files:
        data = path.read_bytes()
        if any(secret in data for secret in secret_values):
            findings.append({"file": path.relative_to(ROOT).as_posix(), "rule": "exact-local-credential", "secret": "[REDACTED]"})
    git = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True)
    tracked = git.stdout.decode(errors="replace").split("\0") if git.returncode == 0 else []
    for name in tracked:
        path = Path(name)
        if not name:
            continue
        if ((path.name.startswith(".env") and not path.name.endswith(".example"))
                or any(p in {"data", "node_modules", ".venv", ".local-tools", "logs", ".aws", ".codex"} for p in path.parts)):
            findings.append({"file": name, "rule": "tracked-private-file", "secret": "[REDACTED]"})
    report = {"public_files_checked": len(files), "exact_credential_findings": findings,
              "git_tracking": "checked" if git.returncode == 0 else "unavailable-no-git-repository",
              "git_history": "requires-gitleaks-git-scan" if git.returncode == 0 else "unavailable-no-git-repository"}
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return bool(findings) or (require_git and git.returncode != 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-git", action="store_true")
    args = parser.parse_args()
    raise SystemExit(audit(args.require_git))
