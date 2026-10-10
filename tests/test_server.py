"""Tests for server utilities and the serve-gunicorn command (no real gunicorn)."""

import sys
import types
from typing import Any

import pytest
from typer.testing import CliRunner

from celery_fastapi.cli import app
from celery_fastapi.server import GunicornApplication, create_gunicorn_app

runner = CliRunner()
SAMPLE = "tests.fixtures.sample_app:celery_app"


class _FakeCfg:
    settings = {"bind", "workers"}

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value


class _FakeBaseApplication:
    def __init__(self) -> None:
        self.cfg = _FakeCfg()
        self.load_config()

    def run(self) -> None:
        self.ran = True


@pytest.fixture
def fake_gunicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    gunicorn = types.ModuleType("gunicorn")
    gunicorn_app = types.ModuleType("gunicorn.app")
    base = types.ModuleType("gunicorn.app.base")
    base.BaseApplication = _FakeBaseApplication  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "gunicorn", gunicorn)
    monkeypatch.setitem(sys.modules, "gunicorn.app", gunicorn_app)
    monkeypatch.setitem(sys.modules, "gunicorn.app.base", base)


def _block_gunicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("gunicorn", "gunicorn.app", "gunicorn.app.base"):
        monkeypatch.setitem(sys.modules, name, None)


def test_create_gunicorn_app_without_gunicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_gunicorn(monkeypatch)
    with pytest.raises(ImportError, match="celery-fastapi\\[gunicorn\\]"):
        create_gunicorn_app(object())


@pytest.mark.usefixtures("fake_gunicorn")
def test_create_gunicorn_app_applies_known_options() -> None:
    sentinel = object()
    gunicorn_app = create_gunicorn_app(
        sentinel, {"bind": "0.0.0.0:1", "workers": None, "unknown": 1}
    )
    assert gunicorn_app.cfg.values == {"bind": "0.0.0.0:1"}  # type: ignore[attr-defined]
    assert gunicorn_app.load() is sentinel


@pytest.mark.usefixtures("fake_gunicorn")
def test_gunicorn_application_run() -> None:
    runner_app = GunicornApplication(object(), {"workers": 2})
    runner_app.run()  # must not raise with the fake base class


def test_serve_gunicorn_requires_gunicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    _block_gunicorn(monkeypatch)
    result = runner.invoke(app, ["serve-gunicorn", SAMPLE])
    assert result.exit_code == 1
    assert "gunicorn not installed" in result.stdout


@pytest.mark.usefixtures("fake_gunicorn")
def test_serve_gunicorn_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class _Recorder:
        def __init__(self, _application: Any, options: dict[str, Any]) -> None:
            captured["options"] = options

        def run(self) -> None:
            captured["ran"] = True

    monkeypatch.setattr("celery_fastapi.server.GunicornApplication", _Recorder)
    result = runner.invoke(
        app, ["serve-gunicorn", SAMPLE, "--bind", "127.0.0.1:9", "-w", "3"]
    )
    assert result.exit_code == 0, result.stdout
    assert captured["ran"] is True
    assert captured["options"]["bind"] == "127.0.0.1:9"
    assert captured["options"]["workers"] == 3
