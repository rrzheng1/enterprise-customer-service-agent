"""Export public API schemas for TypeScript generation; no service startup or secrets."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from check_openapi import schema  # noqa: E402

if __name__ == "__main__":
    target = ROOT / "frontend/openapi.json"
    target.write_text(json.dumps(schema(), ensure_ascii=False, indent=2), encoding="utf-8")
    print("Exported public API schema to frontend/openapi.json")
