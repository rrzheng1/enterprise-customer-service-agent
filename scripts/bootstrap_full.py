"""Versioned migration followed by idempotent demonstration data initialization."""
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, check=True)
    subprocess.run([sys.executable, "scripts/seed_sample_data.py"], cwd=root, check=True)
