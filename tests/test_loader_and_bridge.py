"""Tests for load_celery_app and bridge behaviours."""

import pytest
from celery import Celery
from fastapi.testclient import TestClient

from celery_fastapi import CeleryFastAPIBridge, create_app, load_celery_app


class TestLoadCeleryApp:
    def test_colon_path(self) -> None:
        loaded = load_celery_app("tests.fixtures.sample_app:celery_app")
        assert isinstance(loaded, Celery)

    def test_dot_path(self) -> None:
        loaded = load_celery_app("tests.fixtures.sample_app.celery_app")
        assert loaded.main == "sample"

    def test_not_a_celery_instance(self) -> None:
        with pytest.raises(TypeError):
            load_celery_app("tests.fixtures.sample_app:not_celery")

    def test_missing_attribute(self) -> None:
        with pytest.raises(AttributeError):
            load_celery_app("tests.fixtures.sample_app:missing")

    def test_missing_module(self) -> None:
        with pytest.raises(ImportError):
            load_celery_app("no_such_module_xyz:app")

    def test_create_app_accepts_string(self) -> None:
        fastapi_app = create_app("tests.fixtures.sample_app:celery_app")
        assert any(getattr(r, "path", "") == "/sample/add" for r in fastapi_app.routes)


class TestBridgeEndpoints:
    def test_available_tasks(self, client: TestClient) -> None:
        data = client.get("/available-tasks").json()
        names = {t["name"] for t in data["tasks"]}
        assert {"test_app.add", "test_app.greet"} <= names
        assert data["task_count"] == len(data["tasks"])

    def test_task_filter_and_prefix(self, celery_app: Celery) -> None:
        bridge = CeleryFastAPIBridge(
            celery_app,
            prefix="/v1/",
            task_filter=lambda n: n.endswith("add"),
        )
        paths = {
            r["path"]
            for r in bridge.register_routes() and bridge.get_registered_routes()
        }
        assert "/v1/test_app/add" in paths
        assert "/v1/test_app/multiply" not in paths

    def test_register_routes_idempotent(self, bridge: CeleryFastAPIBridge) -> None:
        first = len(bridge.register_routes().routes)
        assert len(bridge.register_routes().routes) == first

    def test_trigger_rejects_unsafe_names(self, client: TestClient) -> None:
        response = client.post("/trigger", json={"task_name": "a;b", "queue": "celery"})
        assert response.status_code == 422

    def test_revoke_with_payload(self, client: TestClient) -> None:
        response = client.request(
            "DELETE", "/tasks/abc", json={"terminate": True, "signal": "SIGKILL"}
        )
        assert response.status_code == 200
        assert response.json() == {"status": "revoked", "task_id": "abc"}

    def test_batch_revoke(self, client: TestClient) -> None:
        ok = client.post("/tasks/batch/revoke", json={"task_ids": ["a", "b"]})
        assert ok.json()["count"] == 2
        assert client.post("/tasks/batch/revoke", json={}).status_code == 422

    def test_websocket_streams_until_ready(self, client: TestClient) -> None:
        task_id = client.post("/test_app/add", json={"x": 1, "y": 2}).json()["task_id"]
        with client.websocket_connect(f"/tasks/{task_id}/ws") as ws:
            frame = ws.receive_json()
        assert frame["task_id"] == task_id
        assert "state" in frame
