"""Tests for health/ping/worker discovery with mocked Celery inspection."""

import socket

import pytest
from fastapi.testclient import TestClient

PING = "celery.app.control.Inspect.ping"
REGISTERED = "celery.app.control.Inspect.registered"


def test_healthz_explicit_worker_online(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(PING, lambda *_a, **_k: {"celery@w1": {"ok": "pong"}})
    data = client.get("/healthz", params={"worker": "celery@w1"}).json()
    assert data["status"] == "healthy"
    assert data["worker_online"] is True
    assert data["worker_hostname"] == "celery@w1"


def test_healthz_no_worker_is_unhealthy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(PING, lambda *_a, **_k: None)
    data = client.get("/healthz").json()
    assert data["status"] == "unhealthy"
    assert data["worker_online"] is False


def test_healthz_broker_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise ConnectionError("broker down")

    monkeypatch.setattr(PING, boom)
    data = client.get("/healthz", params={"worker": "celery@w1"}).json()
    assert data["broker_connected"] is False
    assert data["status"] == "unhealthy"


def test_ping_discovers_worker_by_hostname(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = f"celery@{socket.gethostname()}"
    monkeypatch.setattr(PING, lambda *_a, **_k: {name: {"ok": "pong"}})
    data = client.get("/ping").json()
    assert data["worker_hostname"] == name
    assert data["online"] is True


def test_ping_discovery_via_env_var(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CELERY_WORKER_HOSTNAME", "celery@custom")
    monkeypatch.setattr(PING, lambda *_a, **_k: {"celery@custom": {"ok": "pong"}})
    assert client.get("/ping").json()["worker_hostname"] == "celery@custom"


def test_ping_single_app_worker_fallback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CELERY_WORKER_HOSTNAME", raising=False)
    monkeypatch.setattr(PING, lambda *_a, **_k: {"celery@other-host": {"ok": "pong"}})
    monkeypatch.setattr(
        REGISTERED, lambda *_a, **_k: {"celery@other-host": ["test_app.add"]}
    )
    assert client.get("/ping").json()["worker_hostname"] == "celery@other-host"


def test_ping_ambiguous_workers_returns_offline(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CELERY_WORKER_HOSTNAME", raising=False)
    workers = {"celery@a-zzz": {"ok": "pong"}, "celery@b-yyy": {"ok": "pong"}}
    monkeypatch.setattr(PING, lambda *_a, **_k: workers)
    monkeypatch.setattr(
        REGISTERED, lambda *_a, **_k: {w: ["test_app.add"] for w in workers}
    )
    data = client.get("/ping").json()
    assert data["online"] is False
    assert data["worker_hostname"] is None
