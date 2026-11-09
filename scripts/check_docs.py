"""Check local links in the authoritative public documentation, without network or secrets."""
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def main():
    files = [ROOT / n for n in ["README.md", "README_CN.md", "SECURITY.md", "CONTRIBUTING.md", "THIRD_PARTY_NOTICES.md", "frontend/README.md"]]
    files += list((ROOT / "docs").rglob("*.md"))
    failures = []
    for file in files:
        for target in re.findall(r"\]\(([^)]+)\)", file.read_text(encoding="utf-8")):
            target = target.strip("<>").split("#")[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (file.parent / unquote(target)).exists():
                failures.append(f"{file.relative_to(ROOT)}: {target}")
    assert not failures, "Broken local documentation links: " + "; ".join(failures)
    print(f"Public documentation links passed ({len(files)} Markdown files)")


if __name__ == "__main__":
    main()
