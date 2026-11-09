"""Compare exported OpenAPI with a deterministic, offline application schema."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from customer_service_app.core.config import Settings, get_settings  # noqa: E402
from customer_service_app.main import create_app  # noqa: E402


def schema():
    # Do not allow an author's private .env or a CI model credential to affect generated contracts.
    settings = Settings(_env_file=None, app_name="Enterprise Customer Service", api_prefix="/api/v1", metrics_enabled=True)
    get_settings.cache_clear()
    from unittest.mock import patch
    with patch("customer_service_app.main.get_settings", return_value=settings):
        return create_app().openapi()


if __name__ == "__main__":
    expected = json.loads((ROOT / "frontend/openapi.json").read_text(encoding="utf-8"))
    assert schema() == expected, "OpenAPI is stale: run scripts/export_openapi.py then npm run api:types --prefix frontend"
    print("OpenAPI matches the actual offline FastAPI contract")
