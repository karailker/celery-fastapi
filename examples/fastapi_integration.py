"""Example of integrating celery-fastapi into an existing FastAPI app.

This demonstrates how to add Celery task endpoints to your existing
FastAPI application alongside your own custom routes.

Run:
    # Start Celery worker
    celery -A examples.celery_app worker --loglevel=info

    # Start FastAPI server
    uvicorn examples.fastapi_integration:app --reload

    # With custom worker hostname for health checks
    export CELERY_WORKER_HOSTNAME="celery@worker1"
    celery -A examples.celery_app worker --hostname worker1
    uvicorn examples.fastapi_integration:app --reload

Endpoints:
    GET  /                      - Root endpoint (custom)
    GET  /health                - Health check (custom)
    POST /api/tasks/*           - Celery task endpoints (auto-generated)
    GET  /api/tasks/tasks/{id}  - Task status
    GET  /api/tasks/healthz     - Celery worker health check
    GET  /api/tasks/ping        - Celery worker ping
"""

from fastapi import FastAPI

from celery_fastapi import CeleryFastAPIBridge
from examples.celery_app import celery_app

# Create your FastAPI application
app = FastAPI(
    title="My Application",
    description="An application with Celery task endpoints",
    version="1.0.0",
)


# Add your custom routes
@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Welcome to My Application"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# Integrate Celery tasks under /api/tasks prefix
bridge = CeleryFastAPIBridge(
    celery_app=celery_app,
    fastapi_app=app,
    prefix="/api/tasks",
    include_status_endpoints=True,
)
bridge.register_routes()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
