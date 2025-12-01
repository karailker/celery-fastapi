"""
Celery FastAPI - Automatic REST API generation for Celery tasks.

This package provides seamless integration between Celery and FastAPI,
automatically generating REST endpoints for all registered Celery tasks.
"""

from celery_fastapi.app import create_app, load_celery_app
from celery_fastapi.core import (
    CeleryFastAPIBridge,
    GenericTaskPayload,
    TaskResponse,
    TaskRevokePayload,
    TaskStatusResponse,
)

__version__ = "0.1.0"
__all__ = [
    "CeleryFastAPIBridge",
    "create_app",
    "load_celery_app",
    "GenericTaskPayload",
    "TaskResponse",
    "TaskStatusResponse",
    "TaskRevokePayload",
    "__version__",
]
