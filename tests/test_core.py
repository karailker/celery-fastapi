"""Tests for the core CeleryFastAPIBridge class."""

from celery import Celery
from fastapi import FastAPI
from fastapi.testclient import TestClient

from celery_fastapi import CeleryFastAPIBridge
from celery_fastapi.core import TaskPayload


class TestCeleryFastAPIBridge:
    """Tests for CeleryFastAPIBridge class."""

    def test_init_with_celery_app_only(self, celery_app: Celery) -> None:
        """Test initialization with only Celery app."""
        bridge = CeleryFastAPIBridge(celery_app)
        assert bridge.celery_app is celery_app
        assert bridge.fastapi_app is not None
        assert isinstance(bridge.fastapi_app, FastAPI)

    def test_init_with_both_apps(
        self, celery_app: Celery, fastapi_app: FastAPI
    ) -> None:
        """Test initialization with both Celery and FastAPI apps."""
        bridge = CeleryFastAPIBridge(celery_app, fastapi_app)
        assert bridge.celery_app is celery_app
        assert bridge.fastapi_app is fastapi_app

    def test_init_with_prefix(self, celery_app: Celery) -> None:
        """Test initialization with URL prefix."""
        bridge = CeleryFastAPIBridge(celery_app, prefix="/api/v1")
        assert bridge.prefix == "/api/v1"

    def test_init_with_trailing_slash_prefix(self, celery_app: Celery) -> None:
        """Test that trailing slash is removed from prefix."""
        bridge = CeleryFastAPIBridge(celery_app, prefix="/api/v1/")
        assert bridge.prefix == "/api/v1"

    def test_register_routes_returns_fastapi_app(
        self, bridge: CeleryFastAPIBridge
    ) -> None:
        """Test that register_routes returns the FastAPI app."""
        result = bridge.register_routes()
        assert result is bridge.fastapi_app

    def test_register_routes_is_idempotent(self, bridge: CeleryFastAPIBridge) -> None:
        """Test that calling register_routes multiple times is safe."""
        bridge.register_routes()
        bridge.register_routes()
        assert bridge._registered is True

    def test_task_endpoints_created(
        self, app_with_routes: FastAPI, celery_app: Celery
    ) -> None:
        """Test that task endpoints are created for registered tasks."""
        routes = [route.path for route in app_with_routes.routes]
        assert "/test_app/add" in routes
        assert "/test_app/multiply" in routes
        assert "/test_app/greet" in routes

    def test_status_endpoints_created(self, app_with_routes: FastAPI) -> None:
        """Test that status endpoints are created."""
        routes = [route.path for route in app_with_routes.routes]
        assert "/tasks/{task_id}" in routes
        assert "/tasks" in routes

    def test_status_endpoints_excluded(self, celery_app: Celery) -> None:
        """Test that status endpoints can be excluded."""
        bridge = CeleryFastAPIBridge(celery_app, include_status_endpoints=False)
        app = bridge.register_routes()
        routes = [route.path for route in app.routes]
        assert "/tasks/{task_id}" not in routes
        assert "/tasks" not in routes

    def test_custom_task_filter(self, celery_app: Celery) -> None:
        """Test custom task filter."""
        bridge = CeleryFastAPIBridge(
            celery_app,
            task_filter=lambda name: name == "test_app.add",
        )
        app = bridge.register_routes()
        routes = [route.path for route in app.routes]
        assert "/test_app/add" in routes
        assert "/test_app/multiply" not in routes

    def test_get_registered_routes(self, bridge: CeleryFastAPIBridge) -> None:
        """Test get_registered_routes method."""
        bridge.register_routes()
        routes = bridge.get_registered_routes()
        assert len(routes) > 0
        assert all("path" in route and "method" in route for route in routes)


class TestTaskPayload:
    """Tests for TaskPayload model."""

    def test_default_values(self) -> None:
        """Test default values for TaskPayload."""
        payload = TaskPayload()
        assert payload.args == []
        assert payload.kwargs == {}

    def test_with_args(self) -> None:
        """Test TaskPayload with args."""
        payload = TaskPayload(args=[1, 2, 3])
        assert payload.args == [1, 2, 3]

    def test_with_kwargs(self) -> None:
        """Test TaskPayload with kwargs."""
        payload = TaskPayload(kwargs={"key": "value"})
        assert payload.kwargs == {"key": "value"}


class TestTaskEndpoints:
    """Tests for task execution endpoints."""

    def test_execute_task(self, client: TestClient) -> None:
        """Test executing a task via endpoint."""
        response = client.post(
            "/test_app/add",
            json={"args": [2, 3], "kwargs": {}},
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_execute_task_with_kwargs(self, client: TestClient) -> None:
        """Test executing a task with kwargs."""
        response = client.post(
            "/test_app/greet",
            json={"args": [], "kwargs": {"name": "World"}},
        )
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data

    def test_execute_task_empty_payload(self, client: TestClient) -> None:
        """Test executing a task with empty payload."""
        response = client.post(
            "/test_app/add",
            json={},
        )
        assert response.status_code == 200


class TestStatusEndpoints:
    """Tests for task status endpoints."""

    def test_get_task_status_not_found(self, client: TestClient) -> None:
        """Test getting status of non-existent task."""
        response = client.get("/tasks/nonexistent-task-id")
        assert response.status_code == 404

    def test_list_all_tasks(self, client: TestClient) -> None:
        """Test listing all tasks."""
        response = client.get("/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "active" in data
        assert "scheduled" in data
        assert "reserved" in data
        assert "revoked" in data
