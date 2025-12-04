"""Example Celery application for demonstration.

Run the Celery worker (include all queues your tasks use):
    celery -A examples.celery_app worker --loglevel=info -Q celery,high_priority

    # Or with custom hostname (requires CELERY_WORKER_HOSTNAME for health checks)
    celery -A examples.celery_app worker --hostname worker1 -Q celery,high_priority

Then run the FastAPI server (choose one):
    # Using CLI
    celery-fastapi serve examples.celery_app:celery_app

    # Using CLI with options
    celery-fastapi serve examples.celery_app:celery_app --port 8000 --reload

    # With custom worker hostname for health checks
    export CELERY_WORKER_HOSTNAME="celery@worker1"
    celery-fastapi serve examples.celery_app:celery_app --port 8000 --reload

    # Using Python module
    python -m celery_fastapi.cli serve examples.celery_app:celery_app
"""

from celery import Celery

# Create Celery app
celery_app = Celery(
    "example_tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="example_tasks.add")
def add(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y


@celery_app.task(name="example_tasks.multiply")
def multiply(x: int, y: int) -> int:
    """Multiply two numbers."""
    return x * y


@celery_app.task(name="example_tasks.greeting", queue="high_priority")
def greeting(name: str) -> str:
    """Generate a greeting message."""
    return f"Hello, {name}!"


@celery_app.task(name="example_tasks.long_running")
def long_running_task(duration: int = 10) -> str:
    """Simulate a long-running task."""
    import time

    time.sleep(duration)
    return f"Completed after {duration} seconds"


if __name__ == "__main__":
    celery_app.start()
