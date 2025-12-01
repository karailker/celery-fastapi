"""Pytest fixtures for celery_fastapi tests."""

import pytest
from celery import Celery
from fastapi import FastAPI
from fastapi.testclient import TestClient

from celery_fastapi import CeleryFastAPIBridge, create_app


@pytest.fixture
def celery_app() -> Celery:
    """Create a test Celery application."""
    app = Celery(
        "test_app",
        broker="memory://",
        backend="cache+memory://",
    )
    app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )

    @app.task(name="test_app.add")
    def add(x: int, y: int) -> int:
        return x + y

    @app.task(name="test_app.multiply")
    def multiply(x: int, y: int) -> int:
        return x * y

    @app.task(name="test_app.greet", queue="high_priority")
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    return app


@pytest.fixture
def fastapi_app() -> FastAPI:
    """Create a test FastAPI application."""
    return FastAPI(title="Test API")


@pytest.fixture
def bridge(celery_app: Celery, fastapi_app: FastAPI) -> CeleryFastAPIBridge:
    """Create a test CeleryFastAPIBridge instance."""
    return CeleryFastAPIBridge(celery_app, fastapi_app)


@pytest.fixture
def app_with_routes(bridge: CeleryFastAPIBridge) -> FastAPI:
    """Create a FastAPI app with registered routes."""
    return bridge.register_routes()


@pytest.fixture
def client(app_with_routes: FastAPI) -> TestClient:
    """Create a test client."""
    return TestClient(app_with_routes)


@pytest.fixture
def created_app(celery_app: Celery) -> FastAPI:
    """Create an app using the create_app factory."""
    return create_app(celery_app)


@pytest.fixture
def created_app_client(created_app: FastAPI) -> TestClient:
    """Create a test client for the created app."""
    return TestClient(created_app)
