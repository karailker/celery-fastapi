"""Application factory for Celery FastAPI."""

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

from celery import Celery
from fastapi import FastAPI

from celery_fastapi.core import CeleryFastAPIBridge


def load_celery_app(celery_app_path: str) -> Celery:
    """
    Load a Celery application from a module path.

    Args:
        celery_app_path: Path to the Celery app in format 'module:attribute'
                        or 'module.attribute'. Examples:
                        - 'myapp.celery:app'
                        - 'celery_app:celery_app'
                        - 'tasks.celery_config:celery'

    Returns:
        The loaded Celery application instance.

    Raises:
        ImportError: If the module cannot be imported.
        AttributeError: If the attribute doesn't exist in the module.
        TypeError: If the attribute is not a Celery instance.
    """
    # Parse the module path
    if ":" in celery_app_path:
        module_path, attr_name = celery_app_path.rsplit(":", 1)
    elif "." in celery_app_path:
        # Try to split on the last dot
        parts = celery_app_path.rsplit(".", 1)
        if len(parts) == 2:
            module_path, attr_name = parts
        else:
            module_path = celery_app_path
            attr_name = "celery_app"
    else:
        module_path = celery_app_path
        attr_name = "celery_app"

    # Add current directory to path if not present
    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    # Try to import as a module first
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        # Try loading as a file path
        module_file = Path(module_path.replace(".", "/") + ".py")
        if module_file.exists():
            spec = importlib.util.spec_from_file_location(module_path, module_file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_path] = module
                spec.loader.exec_module(module)
            else:
                raise ImportError(f"Cannot load module from {module_file}")
        else:
            raise

    celery_app = getattr(module, attr_name)

    if not isinstance(celery_app, Celery):
        raise TypeError(f"Expected Celery instance, got {type(celery_app).__name__}")

    return celery_app


def create_app(
    celery_app: Celery | str,
    *,
    title: str = "Celery FastAPI",
    description: str = "Auto-generated REST API for Celery tasks",
    version: str = "1.0.0",
    prefix: str = "",
    include_status_endpoints: bool = True,
    fastapi_kwargs: dict[str, Any] | None = None,
) -> FastAPI:
    """
    Create a FastAPI application with Celery task endpoints.

    This is the main factory function for creating a complete FastAPI
    application that exposes all Celery tasks as REST endpoints.

    Args:
        celery_app: Either a Celery instance or a string path to load one.
                   String format: 'module:attribute' (e.g., 'myapp:celery_app')
        title: Title for the FastAPI application.
        description: Description for the API documentation.
        version: API version string.
        prefix: URL prefix for all endpoints.
        include_status_endpoints: Whether to include /tasks and /tasks/{id} endpoints.
        fastapi_kwargs: Additional keyword arguments to pass to FastAPI.

    Returns:
        Configured FastAPI application with all routes registered.

    Example:
        ```python
        from celery_fastapi import create_app

        # From a Celery instance
        from myapp import celery_app
        app = create_app(celery_app)

        # From a module path
        app = create_app("myapp.celery:app")

        # With custom settings
        app = create_app(
            celery_app,
            title="My Task API",
            prefix="/api/v1",
        )
        ```
    """
    # Load Celery app if string path provided
    if isinstance(celery_app, str):
        celery_app = load_celery_app(celery_app)

    # Create FastAPI application
    fastapi_kwargs = fastapi_kwargs or {}
    fastapi_app = FastAPI(
        title=title,
        description=description,
        version=version,
        **fastapi_kwargs,
    )

    # Create and configure the bridge
    bridge = CeleryFastAPIBridge(
        celery_app=celery_app,
        fastapi_app=fastapi_app,
        prefix=prefix,
        include_status_endpoints=include_status_endpoints,
    )

    # Register all routes
    bridge.register_routes()

    # Store bridge reference for later access
    fastapi_app.state.celery_bridge = bridge

    return fastapi_app
