"""Offline image smoke: assets, migration/code imports and absence of private config."""
from pathlib import Path


def main():
    root = Path("/app")
    for filename in ["frontend/dist/index.html", "alembic.ini", "migrations/env.py",
                     "src/customer_service_app/main.py", "src/customer_service_policy/policy.py"]:
        assert (root / filename).is_file(), f"Missing image artifact: {filename}"
    assert list((root / "frontend/dist/assets").glob("*.js"))
    assert list((root / "knowledge_base").rglob("*.md"))
    for filename in [".env", ".env.full", "data", ".venv", "frontend/node_modules"]:
        assert not (root / filename).exists(), f"Private artifact found in image: {filename}"
    from customer_service_app.main import create_app
    from customer_service_policy.policy import refund_decision
    assert create_app().openapi()["paths"]["/api/v1/chat/stream"]
    assert not refund_decision({"found": False})["allowed"]
    print("Offline image checks passed: frontend, imports, migrations, knowledge and private-file exclusion")


if __name__ == "__main__":
    main()
