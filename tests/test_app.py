"""Tests for the create_app factory function."""

from celery import Celery
from fastapi import FastAPI
from fastapi.testclient import TestClient

from celery_fastapi import create_app


class TestCreateApp:
    """Tests for create_app factory function."""

    def test_create_app_with_celery_instance(self, celery_app: Celery) -> None:
        """Test creating app with Celery instance."""
        app = create_app(celery_app)
        assert isinstance(app, FastAPI)

    def test_create_app_with_custom_title(self, celery_app: Celery) -> None:
        """Test creating app with custom title."""
        app = create_app(celery_app, title="Custom API")
        assert app.title == "Custom API"

    def test_create_app_with_custom_description(self, celery_app: Celery) -> None:
        """Test creating app with custom description."""
        app = create_app(celery_app, description="My custom description")
        assert app.description == "My custom description"

    def test_create_app_with_custom_version(self, celery_app: Celery) -> None:
        """Test creating app with custom version."""
        app = create_app(celery_app, version="2.0.0")
        assert app.version == "2.0.0"

    def test_create_app_with_prefix(self, celery_app: Celery) -> None:
        """Test creating app with URL prefix."""
        app = create_app(celery_app, prefix="/api/v1")
        routes = [route.path for route in app.routes]
        # Check that task routes have the prefix
        assert any("/api/v1/test_app/add" in route for route in routes)

    def test_create_app_without_status_endpoints(self, celery_app: Celery) -> None:
        """Test creating app without status endpoints."""
        app = create_app(celery_app, include_status_endpoints=False)
        routes = [route.path for route in app.routes]
        assert "/tasks" not in routes
        assert "/tasks/{task_id}" not in routes

    def test_create_app_with_fastapi_kwargs(self, celery_app: Celery) -> None:
        """Test creating app with custom FastAPI kwargs."""
        app = create_app(
            celery_app,
            fastapi_kwargs={
                "docs_url": "/swagger",
                "redoc_url": None,
            },
        )
        assert app.docs_url == "/swagger"
        assert app.redoc_url is None

    def test_create_app_stores_bridge_reference(self, celery_app: Celery) -> None:
        """Test that bridge reference is stored in app state."""
        app = create_app(celery_app)
        assert hasattr(app.state, "celery_bridge")
        assert app.state.celery_bridge is not None

    def test_created_app_routes_work(self, created_app_client: TestClient) -> None:
        """Test that created app routes work correctly."""
        response = created_app_client.post(
            "/test_app/add",
            json={"x": 1, "y": 2},
        )
        assert response.status_code == 200
        assert "task_id" in response.json()

    def test_created_app_openapi(self, created_app: FastAPI) -> None:
        """Test that OpenAPI schema is generated."""
        client = TestClient(created_app)
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "paths" in schema
        assert "/test_app/add" in schema["paths"]
