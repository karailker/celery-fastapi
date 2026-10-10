"""Tests for secure-by-default behaviour: admin gating and API key auth."""

import pytest
from celery import Celery
from fastapi import HTTPException
from fastapi.testclient import TestClient

from celery_fastapi import create_app

ADMIN = [
    ("post", "/purge", None),
    ("post", "/trigger", {"task_name": "sec.add", "queue": "celery"}),
    ("delete", "/tasks/abc", None),
    ("post", "/tasks/batch/revoke", {"task_ids": ["a"]}),
]


@pytest.fixture
def celery_app() -> Celery:
    app = Celery("sec", broker="memory://", backend="cache+memory://")

    @app.task(name="sec.add")
    def add(x: int, y: int) -> int:
        return x + y

    return app


def _call(client: TestClient, method: str, path: str, body: object, **kw: object):
    return client.request(method.upper(), path, json=body, **kw)  # type: ignore[arg-type]


@pytest.mark.parametrize(("method", "path", "body"), ADMIN)
def test_admin_endpoints_disabled_by_default(
    celery_app: Celery, method: str, path: str, body: object
) -> None:
    client = TestClient(create_app(celery_app))
    assert _call(client, method, path, body).status_code in (404, 405)


@pytest.mark.parametrize(("method", "path", "body"), ADMIN)
def test_admin_endpoints_enabled_explicitly(
    celery_app: Celery, method: str, path: str, body: object
) -> None:
    client = TestClient(create_app(celery_app, enable_admin_endpoints=True))
    assert _call(client, method, path, body).status_code not in (404, 405)


def test_get_task_status_still_available_by_default(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app))
    assert client.get("/tasks/abc").status_code == 200


def test_api_key_required_everywhere_except_probes(celery_app: Celery) -> None:
    client = TestClient(
        create_app(celery_app, api_key="s3cret", enable_admin_endpoints=True)
    )
    for method, path, body in [
        ("post", "/sec/add", {"x": 1, "y": 2}),
        ("get", "/tasks/abc", None),
        ("get", "/tasks", None),
        ("get", "/workers", None),
        ("get", "/available-tasks", None),
        *ADMIN,
    ]:
        assert _call(client, method, path, body).status_code == 401, path
        wrong = _call(client, method, path, body, headers={"X-API-Key": "nope"})
        assert wrong.status_code == 401, path

    ok = _call(
        client, "post", "/sec/add", {"x": 1, "y": 2}, headers={"X-API-Key": "s3cret"}
    )
    assert ok.status_code == 200


def test_probes_stay_public_with_api_key(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app, api_key="s3cret"))
    assert client.get("/healthz").status_code == 200
    assert client.get("/ping").status_code == 200


def test_custom_api_key_header(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app, api_key="k", api_key_header="X-Token"))
    assert client.get("/tasks/abc").status_code == 401
    assert client.get("/tasks/abc", headers={"X-Token": "k"}).status_code == 200


def test_websocket_requires_api_key(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app, api_key="k"))
    with (
        pytest.raises(Exception),  # noqa: B017,PT011 - closed with 1008
        client.websocket_connect("/tasks/abc/ws"),
    ):
        pass
    with client.websocket_connect("/tasks/abc/ws?api_key=k") as ws:
        assert ws.receive_json()["task_id"] == "abc"


def test_user_dependencies_apply_to_status_endpoints(celery_app: Celery) -> None:
    def deny() -> None:
        raise HTTPException(status_code=403, detail="no")

    client = TestClient(create_app(celery_app, dependencies=[deny]))
    assert client.get("/tasks/abc").status_code == 403
    assert client.post("/sec/add", json={"x": 1, "y": 2}).status_code == 403
    assert client.get("/healthz").status_code == 200
