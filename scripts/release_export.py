"""Export a clean public source context without depending on a local .git directory.

Never deletes a target, includes .env credentials, or follows links outside the source tree.
"""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIRS = {"src", "frontend", "mcp_services", "migrations", "knowledge_base", "scripts",
               "tests", "docs", "assets", "deploy", ".github"}
PRIVATE_PARTS = {"node_modules", "__pycache__", ".git", ".venv", ".local-tools", "dist",
                 ".pytest_cache", ".ruff_cache", ".vite", ".aws", ".codex", ".agents"}


def public_files(root: Path = ROOT):
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] not in PUBLIC_DIRS and len(relative.parts) != 1:
            continue
        if any(part in PRIVATE_PARTS for part in relative.parts):
            continue
        if path.is_dir():
            continue
        if path.is_symlink():
            raise ValueError(f"Review symlink before release: {relative}")
        name = path.name
        if name.startswith(".env") and not (name == ".env.example" or name.endswith(".example")):
            continue
        if path.suffix.lower() in {".log", ".pem", ".key", ".p12", ".pyc"}:
            continue
        if len(relative.parts) == 1 and not (path.suffix in {".md", ".txt", ".in", ".lock", ".toml", ".yml", ".yaml", ".ini", ".cmd", ".sh"}
                or name in {"Dockerfile", "LICENSE", ".gitignore", ".gitattributes", ".dockerignore", ".gitleaks.toml", ".env.example"}
                or (name.startswith(".env.") and name.endswith(".example"))):
            continue
        yield path


def export(target: Path):
    target = target.resolve()
    if target.exists():
        raise ValueError("Target already exists; choose a new directory (nothing will be deleted)")
    files = list(public_files())
    target.mkdir(parents=True)
    for path in files:
        destination = target / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    print(f"Exported {len(files)} public files; private data/configuration excluded")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    export(parser.parse_args().output)
