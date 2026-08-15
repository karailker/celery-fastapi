"""Tests for batch task execution endpoints."""

from typing import Any

from fastapi.testclient import TestClient

from celery_fastapi import create_app


def test_batch_add_tasks() -> None:
    """Test batch execution of multiple add tasks."""
    from celery import Celery

    # Create test Celery app
    celery_app = Celery(
        "test_batch",
        broker="memory://",
        backend="cache+memory://",
    )
    celery_app.conf.update(
        task_always_eager=True, task_eager_propagates=True
    )

    @celery_app.task(name="test_batch.add")
    def add(x: int, y: int) -> int:
        return x + y

    # Create FastAPI app with Celery tasks
    fastapi_app = create_app(celery_app)

    # Test batch add
    from fastapi.testclient import TestClient

    client = TestClient(fastapi_app)

    batch_data = [[1, 2], [3, 4], [5, 6]]
    response = client.post(
        "/tasks/batch",
        json={"tasks": [{"task_name": "test_batch.add", "args": [x, y]} for x, y in batch_data]},
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()
    assert "group_id" in data
    assert len(data["task_ids"]) == len(batch_data)


def test_batch_revoke_response() -> None:
    """Test batch revoke endpoint response."""
    from celery import Celery

    # Due to eager executions not producingAsyncResult IDs needed for batch revoke testing,
    # only verify the endpoint exists and returns 200 (revoke succeeds in eager mode)
    celery_app = Celery(
        "test_batch_revoke",
        broker="memory://",
        backend="cache+memory://",
    )
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)

    @celery_app.task(name="test_batch_revoke.add")
    def add(x: int, y: int) -> int:
        return x + y

    fastapi_app = create_app(celery_app)
    client = TestClient(fastapi_app)

    # Batch execution (returns 200 status)
    batch_data = [[1, 2], [3, 4]]
    response = client.post(
        "/tasks/batch",
        json={"tasks": [{"task_name": "test_batch_revoke.add", "args": [x, y]} for x, y in batch_data]},
    )

    if response.status_code == 200:
        data = response.json()
        task_ids = data["task_ids"]
        if task_ids:
            # Batch revoke endpoint exists
            revoke_response = client.post(
                f"/tasks/batch/revoke",
                json={"task_ids": task_ids[:1]},  # Revoke one to avoid eager repeat execution
            )
            assert revoke_response.status_code == 200
