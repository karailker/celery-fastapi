"""Tests for server utilities."""

import sys
from unittest.mock import MagicMock

import pytest

from celery_fastapi.server import GunicornApplication, create_gunicorn_app


def test_create_gunicorn_app_without_gunicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "gunicorn", None)
    monkeypatch.setitem(sys.modules, "gunicorn.app", None)
    monkeypatch.setitem(sys.modules, "gunicorn.app.base", None)

    with pytest.raises(ImportError, match="celery-fastapi\\[gunicorn\\]"):
        create_gunicorn_app(object())


def test_gunicorn_application_runs_wrapped_app(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = MagicMock()
    monkeypatch.setattr(
        "celery_fastapi.server.create_gunicorn_app", lambda *_args: fake
    )

    runner = GunicornApplication(object(), {"bind": "127.0.0.1:0"})
    runner.run()

    fake.run.assert_called_once_with()
