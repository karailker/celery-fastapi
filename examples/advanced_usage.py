"""Advanced example demonstrating all celery-fastapi features.

This example shows:
- Full Celery task options (countdown, priority, queue, time limits)
- Task filtering
- Custom FastAPI configuration
- Health check and monitoring endpoints
- Production-ready setup

Run:
    # Start Celery worker
    celery -A examples.celery_app worker --loglevel=info -Q celery,high_priority

    # Or with custom hostname
    celery -A examples.celery_app worker --hostname worker1 -Q celery,high_priority

    # Start FastAPI server
    uvicorn examples.advanced_usage:app --reload

    # With custom worker hostname for health checks
    export CELERY_WORKER_HOSTNAME="celery@worker1"
    uvicorn examples.advanced_usage:app --reload

Or with gunicorn for production:
    gunicorn examples.advanced_usage:app -w 4 -k uvicorn.workers.UvicornWorker
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from celery_fastapi import CeleryFastAPIBridge
from examples.celery_app import celery_app

# Option 1: Quick setup with create_app
# app = create_app(celery_app)

# Option 2: Full control with CeleryFastAPIBridge
app = FastAPI(
    title="Advanced Celery FastAPI",
    description="""
    Advanced example demonstrating full celery-fastapi integration.

    ## Features
    - Execute any Celery task via REST API
    - Full Celery options support (countdown, priority, queue, etc.)
    - Task status monitoring
    - Worker and queue inspection
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """API root with links to documentation."""
    return {
        "message": "Celery FastAPI Advanced Example",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy", "celery_app": celery_app.main}


# Create bridge with advanced options
bridge = CeleryFastAPIBridge(
    celery_app=celery_app,
    fastapi_app=app,
    prefix="/api/v1",
    include_status_endpoints=True,
    # Filter out internal tasks
    task_filter=lambda name: not name.startswith("celery."),
)

# Register routes
bridge.register_routes()


# Example: Custom endpoint that uses Celery directly
@app.post("/api/v1/batch/add")
async def batch_add(numbers: list[tuple[int, int]]):
    """Execute multiple add tasks in parallel.

    Example request body:
    ```json
    [[1, 2], [3, 4], [5, 6]]
    ```
    """
    from celery import group

    # Create a group of tasks
    job = group(
        celery_app.signature("example_tasks.add", args=pair) for pair in numbers
    )

    # Execute the group
    result = job.apply_async()

    return {
        "group_id": result.id,
        "task_ids": [r.id for r in result.children or []],
        "message": f"Submitted {len(numbers)} add tasks",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
