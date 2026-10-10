"""Tests for CLI commands against an importable sample app."""

from typing import Any

import pytest
from typer.testing import CliRunner

from celery_fastapi import cli
from celery_fastapi.cli import app

runner = CliRunner()
SAMPLE = "tests.fixtures.sample_app:celery_app"


def test_routes_lists_task_endpoint() -> None:
    result = runner.invoke(app, ["routes", SAMPLE])
    assert result.exit_code == 0
    assert "/sample/add" in result.stdout


def test_routes_with_prefix() -> None:
    result = runner.invoke(app, ["routes", SAMPLE, "--prefix", "/api"])
    assert result.exit_code == 0
    assert "/api/sample/add" in result.stdout


def test_tasks_lists_custom_tasks() -> None:
    result = runner.invoke(app, ["tasks", SAMPLE])
    assert result.exit_code == 0
    assert "sample.add" in result.stdout


@pytest.mark.parametrize("command", ["routes", "tasks", "workers", "serve"])
def test_commands_fail_on_unknown_app(command: str) -> None:
    result = runner.invoke(app, [command, "no_such_module_xyz:app"])
    assert result.exit_code == 1
    assert "Error loading Celery app" in result.stdout


def test_workers_without_active_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("celery.app.control.Inspect.ping", lambda *_a, **_k: None)
    result = runner.invoke(app, ["workers", SAMPLE])
    assert result.exit_code == 0
    assert "No active workers" in result.stdout


def test_workers_prints_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "celery.app.control.Inspect.ping",
        lambda *_a, **_k: {"w1@h": {"ok": "pong"}},
    )
    monkeypatch.setattr(
        "celery.app.control.Inspect.stats",
        lambda *_a, **_k: {"w1@h": {"pool": {"implementation": "prefork"}}},
    )
    result = runner.invoke(app, ["workers", SAMPLE])
    assert result.exit_code == 0
    assert "w1@h" in result.stdout
    assert "prefork" in result.stdout


def test_serve_single_worker_runs_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}
    monkeypatch.setattr(
        "uvicorn.run", lambda target, **kw: calls.update(target=target, **kw)
    )
    result = runner.invoke(app, ["serve", SAMPLE, "--port", "9001"])
    assert result.exit_code == 0
    assert calls["port"] == 9001
    assert calls["workers"] == 1
    assert not isinstance(calls["target"], str)


def test_serve_multi_worker_uses_import_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    monkeypatch.setattr(
        "uvicorn.run", lambda target, **kw: calls.update(target=target, **kw)
    )
    monkeypatch.delenv("CELERY_FASTAPI_CELERY_APP", raising=False)
    result = runner.invoke(app, ["serve", SAMPLE, "--workers", "2", "--prefix", "/x"])
    assert result.exit_code == 0
    assert calls["target"] == "celery_fastapi.cli:_create_app_from_env"
    assert calls["workers"] == 2


def test_create_app_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELERY_FASTAPI_CELERY_APP", SAMPLE)
    monkeypatch.setenv("CELERY_FASTAPI_PREFIX", "/env")
    fastapi_app = cli._create_app_from_env()
    paths = {r.path for r in fastapi_app.routes}  # type: ignore[attr-defined]
    assert "/env/sample/add" in paths


def test_create_app_from_env_requires_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CELERY_FASTAPI_CELERY_APP", raising=False)
    with pytest.raises(ValueError, match="CELERY_FASTAPI_CELERY_APP"):
        cli._create_app_from_env()
