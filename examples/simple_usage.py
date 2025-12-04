"""Simple example using create_app factory function.

This is the quickest way to create a FastAPI app
with Celery task endpoints.

Run with uvicorn:
    # Start Celery worker first
    celery -A examples.celery_app worker --loglevel=info

    # Then start FastAPI
    uvicorn examples.simple_usage:app --reload

Or use the CLI directly:
    celery-fastapi serve examples.celery_app:celery_app --reload

For custom worker hostnames (enables accurate health checks):
    export CELERY_WORKER_HOSTNAME="celery@worker1"
    celery -A examples.celery_app worker --hostname worker1
    celery-fastapi serve examples.celery_app:celery_app --reload

API Documentation will be available at:
    http://localhost:8000/docs (Swagger UI)
    http://localhost:8000/redoc (ReDoc)

Health Monitoring:
    http://localhost:8000/healthz (Worker health check)
    http://localhost:8000/ping (Worker ping)
"""

from celery_fastapi import create_app
from examples.celery_app import celery_app

# Create the FastAPI app with one line
app = create_app(
    celery_app,
    title="Simple Task API",
    description="Automatically generated API for Celery tasks",
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
