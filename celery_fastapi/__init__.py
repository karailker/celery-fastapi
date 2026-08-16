"""
Celery FastAPI - Automatic REST API generation for Celery tasks.

This package provides seamless integration between Celery and FastAPI,
automatically generating REST endpoints for all registered Celery tasks.
"""

from celery_fastapi.app import create_app, load_celery_app
from celery_fastapi.core import (
    BaseRateLimitStorage,
    CeleryFastAPIBridge,
    GenericTaskPayload,
    InMemoryRateLimitStorage,
    TaskResponse,
    TaskRevokePayload,
    TaskStatusResponse,
)

__version__ = "0.0.0"
__all__ = [
    "BaseRateLimitStorage",
    "CeleryFastAPIBridge",
    "create_app",
    "GenericTaskPayload",
    "InMemoryRateLimitStorage",
    "load_celery_app",
    "TaskResponse",
    "TaskRevokePayload",
    "TaskStatusResponse",
    "__version__",
]
