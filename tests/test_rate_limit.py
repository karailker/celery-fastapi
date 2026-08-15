"""Tests for rate limiting on task endpoints."""

from celery import Celery
from fastapi.testclient import TestClient

from celery_fastapi import create_app


def _make_app_with_ratelimit(rate_limit: int = 2) -> TestClient:
    """Create a test app with rate limiting enabled."""
    celery_app = Celery(
        "test_ratelimit",
        broker="memory://",
        backend="cache+memory://",
    )
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)

    @celery_app.task(name="test_ratelimit.add")
    def add(x: int, y: int) -> int:
        return x + y

    fastapi_app = create_app(celery_app, rate_limit=rate_limit)
    return TestClient(fastapi_app)


def test_ratelimit_allows_under_limit() -> None:
    """Test that requests under the rate limit succeed."""
    client = _make_app_with_ratelimit(rate_limit=3)

    for _ in range(3):
        response = client.post("/test_ratelimit/add", json={"x": 1, "y": 2})
        assert response.status_code == 200


def test_ratelimit_rejects_over_limit() -> None:
    """Test that requests exceeding the rate limit return 429."""
    client = _make_app_with_ratelimit(rate_limit=2)

    # First two requests succeed
    for _ in range(2):
        response = client.post("/test_ratelimit/add", json={"x": 1, "y": 2})
        assert response.status_code == 200

    # Third request should be rate limited
    response = client.post("/test_ratelimit/add", json={"x": 1, "y": 2})
    assert response.status_code == 429
    assert (
        "limit exceeded" in response.text.lower() or "too many" in response.text.lower()
    )
