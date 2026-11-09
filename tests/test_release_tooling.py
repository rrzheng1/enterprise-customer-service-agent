"""Release boundaries: no credentials/data in source exports, reproducible preparation."""
import importlib.util
from pathlib import Path


def module(name):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(name, root / "scripts" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_public_export_keeps_templates_docs_and_fixtures_but_not_private_files(tmp_path):
    export = module("release_export")
    for filename in [".env", ".env.full", ".env.demo.example", ".env.example", "README.md",
                     "docs/guide.md", "tests/fixture.json", "frontend/node_modules/pkg/key.txt",
                     "data/customer.json", ".venv/token.txt", "src/app.py"]:
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    files = {p.relative_to(tmp_path).as_posix() for p in export.public_files(tmp_path)}
    assert {".env.example", ".env.demo.example", "docs/guide.md", "tests/fixture.json", "src/app.py"} <= files
    assert not {".env", ".env.full", "data/customer.json", ".venv/token.txt", "frontend/node_modules/pkg/key.txt"} & files


def test_isolated_configuration_does_not_change_source_and_keeps_generated_credentials(tmp_path):
    prepare = module("prepare_full")
    source = tmp_path / "source.env"
    source.write_text("LLM_API_KEY=not-a-real-test-key\nLLM_MODEL=configured-model\nLLM_BASE_URL=https://example.test/v1\nEMBEDDING_MODEL=configured-embedding\n")
    before = source.read_bytes()
    target = tmp_path / "independent/.env.release"
    prepare.prepare(target, source, {"FULL_HTTP_PORT": "18002"})
    from dotenv import dotenv_values
    first = dotenv_values(target)
    prepare.prepare(target, source, {"FULL_HTTP_PORT": "18002"})
    second = dotenv_values(target)
    assert source.read_bytes() == before
    assert first["DATABASE_URL"] == second["DATABASE_URL"]
    assert second["FULL_HTTP_PORT"] == "18002"
    assert second["LLM_MODEL"] == "configured-model"
    assert second["EMBEDDING_MODEL"] == "configured-embedding"


def test_compose_selection_propagates_to_explicit_acceptance_subprocesses(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import os
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    runner = module("run_full")
    monkeypatch.setenv("CUSTOMER_AGENT_ENV_FILE", "previous.env")
    monkeypatch.setenv("CUSTOMER_AGENT_PROJECT", "previous-project")
    monkeypatch.setattr(runner.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0))
    target = tmp_path / ".env.review"
    command = runner.docker_command(target, "isolated-review")
    assert command[command.index("--project-name") + 1] == "isolated-review"
    assert os.environ["CUSTOMER_AGENT_PROJECT"] == "isolated-review"
    assert os.environ["CUSTOMER_AGENT_ENV_FILE"] == str(target.resolve())
