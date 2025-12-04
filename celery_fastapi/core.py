"""Core functionality for Celery FastAPI."""

import inspect
from collections.abc import Callable
from datetime import datetime
from typing import Any, get_type_hints

from celery import Celery
from celery.result import AsyncResult
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, create_model

# Celery execution options - shared fields for all task payloads
CELERY_OPTIONS_FIELDS: dict[str, Any] = {
    "countdown": (
        float | None,
        Field(default=None, description="Seconds to wait before executing"),
    ),
    "eta": (
        datetime | None,
        Field(default=None, description="Datetime when task should execute (UTC)"),
    ),
    "expires": (
        float | datetime | None,
        Field(default=None, description="Task expiration time"),
    ),
    "retry": (
        bool | None,
        Field(default=None, description="Retry on failure"),
    ),
    "retry_policy": (
        dict[str, Any] | None,
        Field(default=None, description="Retry policy options"),
    ),
    "queue": (
        str | None,
        Field(default=None, description="Override the default queue"),
    ),
    "exchange": (
        str | None,
        Field(default=None, description="Override the default exchange"),
    ),
    "routing_key": (
        str | None,
        Field(default=None, description="Override the default routing key"),
    ),
    "priority": (
        int | None,
        Field(default=None, ge=0, le=9, description="Task priority (0-9)"),
    ),
    "serializer": (
        str | None,
        Field(default=None, description="Serializer (json, pickle, yaml, msgpack)"),
    ),
    "compression": (
        str | None,
        Field(default=None, description="Compression method"),
    ),
    "headers": (
        dict[str, Any] | None,
        Field(default=None, description="Custom message headers"),
    ),
    "link": (
        list[str] | None,
        Field(default=None, description="Tasks to call on success"),
    ),
    "link_error": (
        list[str] | None,
        Field(default=None, description="Tasks to call on error"),
    ),
    "task_id": (
        str | None,
        Field(default=None, description="Custom task ID"),
    ),
    "shadow": (
        str | None,
        Field(default=None, description="Override task name in logs"),
    ),
    "ignore_result": (
        bool | None,
        Field(default=None, description="Don't store the result"),
    ),
    "time_limit": (
        float | None,
        Field(default=None, description="Hard time limit (seconds)"),
    ),
    "soft_time_limit": (
        float | None,
        Field(default=None, description="Soft time limit (seconds)"),
    ),
}


class GenericTaskPayload(BaseModel):
    """Generic payload for triggering any task by name."""

    task_name: str = Field(description="Full task name (e.g., 'myapp.tasks.add')")
    queue: str = Field(description="Queue to send the task to (required)")
    args: list[Any] = Field(
        default_factory=list, description="Positional arguments for the task"
    )
    kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Keyword arguments for the task"
    )

    # Celery execution options
    countdown: float | None = Field(default=None, description="Seconds to wait")
    eta: datetime | None = Field(default=None, description="Execute at datetime (UTC)")
    expires: float | datetime | None = Field(default=None, description="Expiration")
    retry: bool | None = Field(default=None, description="Retry on failure")
    retry_policy: dict[str, Any] | None = Field(
        default=None, description="Retry policy"
    )
    exchange: str | None = Field(default=None, description="Override exchange")
    routing_key: str | None = Field(default=None, description="Override routing key")
    priority: int | None = Field(default=None, ge=0, le=9, description="Priority (0-9)")
    serializer: str | None = Field(default=None, description="Serializer")
    compression: str | None = Field(default=None, description="Compression")
    headers: dict[str, Any] | None = Field(default=None, description="Custom headers")
    task_id: str | None = Field(default=None, description="Custom task ID")
    ignore_result: bool | None = Field(default=None, description="Don't store result")
    time_limit: float | None = Field(default=None, description="Hard time limit")
    soft_time_limit: float | None = Field(default=None, description="Soft time limit")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_name": "myapp.tasks.add",
                    "queue": "celery",
                    "args": [1, 2],
                    "kwargs": {},
                },
                {
                    "task_name": "myapp.tasks.process",
                    "queue": "high_priority",
                    "args": [],
                    "kwargs": {"data": "test"},
                    "countdown": 60,
                },
            ]
        }
    }


def _python_type_to_json_type(py_type: type) -> str:
    """Convert Python type to JSON schema type string."""
    if py_type in (int,):
        return "integer"
    elif py_type in (float,):
        return "number"
    elif py_type in (bool,):
        return "boolean"
    elif py_type in (str,):
        return "string"
    elif py_type in (list, tuple):
        return "array"
    elif py_type in (dict,):
        return "object"
    return "string"


def _create_task_payload_model(
    task_name: str,
    task_func: Callable[..., Any],
    default_queue: str,
) -> type[BaseModel]:
    """
    Create a dynamic Pydantic model for a specific task based on its signature.

    This generates a model with the actual parameter names and types from the task.
    """
    # Get function signature and type hints
    sig = inspect.signature(task_func)
    try:
        type_hints = get_type_hints(task_func)
    except Exception:  # noqa: BLE001
        type_hints = {}

    # Build field definitions for task arguments
    field_definitions: dict[str, Any] = {}
    example_kwargs: dict[str, Any] = {}

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        # Get type annotation
        param_type = type_hints.get(param_name, Any)

        # Handle Optional types and defaults
        has_default = param.default is not inspect.Parameter.empty
        default_value = param.default if has_default else ...

        # Create example value based on type
        if param_type is int:
            example_kwargs[param_name] = 1 if not has_default else default_value
        elif param_type is float:
            example_kwargs[param_name] = 1.0 if not has_default else default_value
        elif param_type is str:
            example_kwargs[param_name] = "example" if not has_default else default_value
        elif param_type is bool:
            example_kwargs[param_name] = True if not has_default else default_value
        elif has_default:
            example_kwargs[param_name] = default_value

        # Make field optional if it has a default
        if has_default:
            field_definitions[param_name] = (
                param_type | None,
                Field(default=default_value, description=f"Parameter: {param_name}"),
            )
        else:
            field_definitions[param_name] = (
                param_type,
                Field(description=f"Parameter: {param_name} (required)"),
            )

    # Add Celery options fields
    field_definitions.update(CELERY_OPTIONS_FIELDS)

    # Create the model class name
    model_name = f"{task_name.replace('.', '_').title().replace('_', '')}Payload"

    # Create and return the dynamic model
    model: type[BaseModel] = create_model(model_name, **field_definitions)
    model.__doc__ = f"Payload for {task_name} task. Default queue: {default_queue}"

    # Set model config for examples
    if example_kwargs:
        model.model_config = {"json_schema_extra": {"examples": [example_kwargs]}}

    return model


class TaskResponse(BaseModel):
    """Response model for task submission."""

    task_id: str = Field(description="Unique identifier for the submitted task")
    status: str = Field(default="PENDING", description="Initial task status")


class TaskStatusResponse(BaseModel):
    """Response model for task status."""

    task_id: str
    state: str
    result: Any | None = None
    traceback: str | None = None
    date_done: datetime | None = None
    info: dict[str, Any] | None = None


class TaskListResponse(BaseModel):
    """Response model for listing all tasks."""

    active: dict[str, list[dict[str, Any]]]
    scheduled: dict[str, list[dict[str, Any]]]
    reserved: dict[str, list[dict[str, Any]]]
    revoked: dict[str, list[str]]


class TaskRevokePayload(BaseModel):
    """Payload for revoking tasks."""

    terminate: bool = Field(
        default=False, description="Terminate the task if currently executing"
    )
    signal: str = Field(
        default="SIGTERM", description="Signal to send (SIGTERM, SIGKILL)"
    )


class CeleryFastAPIBridge:
    """
    Bridge class that connects Celery tasks to FastAPI endpoints.

    This class automatically generates REST API endpoints for all registered
    Celery tasks, providing a seamless way to trigger and monitor tasks via HTTP.

    Important: This bridge only exposes and manages tasks registered in the
    provided Celery app instance, not tasks from the entire cluster.

    Example:
        ```python
        from celery import Celery
        from fastapi import FastAPI
        from celery_fastapi import CeleryFastAPIBridge

        celery_app = Celery('tasks', broker='redis://localhost:6379/0')
        fastapi_app = FastAPI()

        bridge = CeleryFastAPIBridge(celery_app, fastapi_app)
        bridge.register_routes()
        ```
    """

    def __init__(
        self,
        celery_app: Celery,
        fastapi_app: FastAPI | None = None,
        *,
        prefix: str = "",
        include_status_endpoints: bool = True,
        task_filter: Callable[[str], bool] | None = None,
    ) -> None:
        """
        Initialize the Celery FastAPI Bridge.

        Args:
            celery_app: The Celery application instance.
            fastapi_app: Optional FastAPI application instance. If not provided,
                        a new one will be created.
            prefix: URL prefix for all generated endpoints.
            include_status_endpoints: Whether to include task status and listing endpoints.
            task_filter: Optional callable to filter which tasks to expose.
                        Takes task name, returns True to include, False to exclude.
        """
        self.celery_app = celery_app
        self.fastapi_app = fastapi_app or FastAPI()
        self.prefix = prefix.rstrip("/")
        self.include_status_endpoints = include_status_endpoints
        self.task_filter = task_filter or (lambda name: not name.startswith("celery."))
        self._registered = False

        # Store the registered task names from THIS app only
        self._app_task_names: set[str] = set()
        for name in self.celery_app.tasks:
            if self.task_filter(name):
                self._app_task_names.add(name)

    def register_routes(self) -> FastAPI:
        """
        Register all Celery task routes on the FastAPI application.

        Returns:
            The FastAPI application with registered routes.
        """
        if self._registered:
            return self.fastapi_app

        self._register_task_endpoints()

        if self.include_status_endpoints:
            self._register_status_endpoints()

        self._registered = True
        return self.fastapi_app

    def _register_task_endpoints(self) -> None:
        """Register POST endpoints for each Celery task."""
        # Get the default queue name from Celery config (defaults to 'celery')
        default_queue = self.celery_app.conf.task_default_queue or "celery"

        for name, task in self.celery_app.tasks.items():
            if not self.task_filter(name):
                continue

            queue_name = getattr(task, "queue", None) or default_queue
            endpoint = name.replace(".", "/")
            route_path = f"{self.prefix}/{endpoint}"

            # Create endpoint handler with proper closure
            self._create_task_endpoint(name, queue_name, route_path)

    def _create_task_endpoint(
        self, task_name: str, queue_name: str, route_path: str
    ) -> None:
        """Create a POST endpoint for a specific task with custom payload model."""
        # Get the task function to inspect its signature
        task = self.celery_app.tasks.get(task_name)
        task_func = getattr(task, "run", None) if task else None

        # Create a custom payload model for this task
        if task_func:
            PayloadModel = _create_task_payload_model(task_name, task_func, queue_name)
        else:
            # Fallback to generic model if we can't inspect the task
            PayloadModel = GenericTaskPayload

        # Create the endpoint handler
        async def run_task(
            payload: PayloadModel,  # type: ignore[valid-type]
            task_name_override: str | None = Query(
                default=None,
                alias="_task_name",
                description=f"Override task name (default: {task_name})",
            ),
            queue_override: str | None = Query(
                default=None,
                alias="_queue",
                description=f"Override queue (default: {queue_name})",
            ),
        ) -> TaskResponse:
            """Execute a Celery task asynchronously."""
            # Determine actual task name and queue
            actual_task_name = task_name_override or task_name
            actual_queue = (
                queue_override or getattr(payload, "queue", None) or queue_name
            )

            # Extract task arguments from payload
            # Get all field names that are task parameters (not Celery options)
            celery_option_names = set(CELERY_OPTIONS_FIELDS.keys())
            task_kwargs: dict[str, Any] = {}

            # Access model_fields from the class, not the instance (Pydantic V2.11+)
            payload_fields = type(payload).model_fields  # type: ignore[attr-defined]
            for field_name in payload_fields:
                if field_name not in celery_option_names:
                    value = getattr(payload, field_name, None)
                    if value is not None:
                        task_kwargs[field_name] = value

            # Build send_task options
            send_options: dict[str, Any] = {
                "args": [],
                "kwargs": task_kwargs,
                "queue": actual_queue,
            }

            # Add Celery options if set
            for opt_name in celery_option_names:
                value = getattr(payload, opt_name, None)
                if value is not None and opt_name != "queue":  # queue handled above
                    send_options[opt_name] = value

            result = self.celery_app.send_task(actual_task_name, **send_options)
            return TaskResponse(task_id=result.id, status="PENDING")

        # Set a descriptive name for the endpoint
        run_task.__name__ = f"run_{task_name.replace('.', '_')}"
        run_task.__doc__ = f"Execute '{task_name}' task. Default queue: '{queue_name}'."

        self.fastapi_app.post(
            route_path,
            response_model=TaskResponse,
            tags=["tasks"],
            summary=f"Run {task_name}",
            description=f"Submit '{task_name}' task for async execution.\n\nDefault queue: `{queue_name}`\n\nUse `_task_name` and `_queue` query params to override.",
        )(run_task)

    def _register_status_endpoints(self) -> None:
        """Register task status, listing, and control endpoints."""

        @self.fastapi_app.get(
            f"{self.prefix}/tasks/{{task_id}}",
            response_model=TaskStatusResponse,
            tags=["task-status"],
            summary="Get task status",
        )
        async def get_task_status(task_id: str) -> TaskStatusResponse:
            """
            Get the status of a specific task by its ID.

            Returns detailed information including state, result, and traceback.

            Raises:
                HTTPException: 404 if the task is not found.
            """
            result = AsyncResult(task_id, app=self.celery_app)

            if result.state == "PENDING":
                raise HTTPException(
                    status_code=404, detail=f"Task '{task_id}' not found"
                )

            # Build info dict with additional metadata
            info: dict[str, Any] = {}
            if hasattr(result, "info") and result.info:
                if isinstance(result.info, dict):
                    info = result.info
                elif isinstance(result.info, Exception):
                    info = {"error": str(result.info)}

            return TaskStatusResponse(
                task_id=task_id,
                state=result.state,
                result=result.result if result.ready() else None,
                traceback=result.traceback,
                date_done=result.date_done,
                info=info if info else None,
            )

        @self.fastapi_app.delete(
            f"{self.prefix}/tasks/{{task_id}}",
            tags=["task-status"],
            summary="Revoke a task",
        )
        async def revoke_task(
            task_id: str,
            payload: TaskRevokePayload | None = None,
        ) -> dict[str, str]:
            """
            Revoke a pending or running task.

            Args:
                task_id: The task ID to revoke.
                payload: Optional revoke options (terminate, signal).

            Returns:
                Confirmation of revocation request.
            """
            payload = payload or TaskRevokePayload()
            self.celery_app.control.revoke(
                task_id,
                terminate=payload.terminate,
                signal=payload.signal,
            )
            return {"status": "revoked", "task_id": task_id}

        @self.fastapi_app.get(
            f"{self.prefix}/tasks/{{task_id}}/result",
            tags=["task-status"],
            summary="Get task result",
        )
        async def get_task_result(task_id: str, timeout: float | None = None) -> Any:
            """
            Get the result of a completed task.

            Args:
                task_id: The task ID.
                timeout: Optional timeout in seconds to wait for result.

            Returns:
                The task result.

            Raises:
                HTTPException: 404 if not found, 202 if not ready, 500 on failure.
            """
            result = AsyncResult(task_id, app=self.celery_app)

            if result.state == "PENDING":
                raise HTTPException(
                    status_code=404, detail=f"Task '{task_id}' not found"
                )

            if not result.ready():
                if timeout:
                    try:
                        return result.get(timeout=timeout)
                    except TimeoutError as exc:
                        raise HTTPException(
                            status_code=202,
                            detail=f"Task '{task_id}' not ready within timeout",
                        ) from exc
                raise HTTPException(
                    status_code=202,
                    detail=f"Task '{task_id}' is still {result.state}",
                )

            if result.failed():
                raise HTTPException(
                    status_code=500,
                    detail=f"Task '{task_id}' failed: {result.traceback}",
                )

            return result.result

        @self.fastapi_app.get(
            f"{self.prefix}/tasks",
            response_model=TaskListResponse,
            tags=["task-status"],
            summary="List all tasks",
        )
        async def list_all_tasks() -> TaskListResponse:
            """
            List active, scheduled, reserved, and revoked tasks for THIS app only.

            Only shows tasks that are registered in this Celery application,
            filtering out tasks from other apps in the cluster.
            """
            inspector = self.celery_app.control.inspect()

            # Helper to filter tasks by this app's registered task names
            def filter_tasks(
                tasks_by_worker: dict[str, list[dict[str, Any]]] | None,
            ) -> dict[str, list[dict[str, Any]]]:
                if not tasks_by_worker:
                    return {}
                filtered: dict[str, list[dict[str, Any]]] = {}
                for worker, task_list in tasks_by_worker.items():
                    filtered_list = [
                        t for t in task_list if t.get("name") in self._app_task_names
                    ]
                    if filtered_list:
                        filtered[worker] = filtered_list
                return filtered

            return TaskListResponse(
                active=filter_tasks(inspector.active()),
                scheduled=filter_tasks(inspector.scheduled()),
                reserved=filter_tasks(inspector.reserved()),
                revoked=inspector.revoked()
                or {},  # Revoked is just task IDs, can't filter
            )

        @self.fastapi_app.get(
            f"{self.prefix}/workers",
            tags=["workers"],
            summary="List workers",
        )
        async def list_workers() -> dict[str, Any]:
            """
            Get information about Celery workers that can execute THIS app's tasks.

            Filters registered tasks to only show tasks from this application.
            """
            inspector = self.celery_app.control.inspect()

            # Filter registered tasks to only show this app's tasks
            registered = inspector.registered() or {}
            filtered_registered: dict[str, list[str]] = {}
            for worker, tasks in registered.items():
                filtered_tasks = [t for t in tasks if t in self._app_task_names]
                if filtered_tasks:
                    filtered_registered[worker] = filtered_tasks

            return {
                "ping": inspector.ping() or {},
                "stats": inspector.stats() or {},
                "registered": filtered_registered,
                "active_queues": inspector.active_queues() or {},
            }

        @self.fastapi_app.get(
            f"{self.prefix}/available-tasks",
            tags=["tasks"],
            summary="List available tasks",
        )
        async def list_available_tasks() -> dict[str, Any]:
            """
            List all tasks available in THIS Celery application.

            Returns the task names and their configuration (queue, etc.)
            that are registered in this specific app instance.
            """
            # Get the default queue name from Celery config
            default_queue = self.celery_app.conf.task_default_queue or "celery"

            tasks_info: list[dict[str, Any]] = []
            for name in sorted(self._app_task_names):
                task = self.celery_app.tasks.get(name)
                if task:
                    tasks_info.append(
                        {
                            "name": name,
                            "queue": getattr(task, "queue", None) or default_queue,
                            "rate_limit": getattr(task, "rate_limit", None),
                            "time_limit": getattr(task, "time_limit", None),
                            "soft_time_limit": getattr(task, "soft_time_limit", None),
                            "max_retries": getattr(task, "max_retries", None),
                            "default_retry_delay": getattr(
                                task, "default_retry_delay", None
                            ),
                        }
                    )

            return {
                "app_name": self.celery_app.main,
                "task_count": len(tasks_info),
                "tasks": tasks_info,
            }

        @self.fastapi_app.get(
            f"{self.prefix}/queues",
            tags=["workers"],
            summary="List active queues",
        )
        async def list_queues() -> dict[str, Any]:
            """Get information about active queues."""
            inspector = self.celery_app.control.inspect()
            return {"queues": inspector.active_queues() or {}}

        @self.fastapi_app.post(
            f"{self.prefix}/purge",
            tags=["workers"],
            summary="Purge all tasks",
        )
        async def purge_tasks() -> dict[str, int]:
            """Purge all pending tasks from the queue."""
            count = self.celery_app.control.purge()
            return {"purged": count or 0}

        @self.fastapi_app.post(
            f"{self.prefix}/trigger",
            response_model=TaskResponse,
            tags=["tasks"],
            summary="Trigger any task",
        )
        async def trigger_generic_task(payload: GenericTaskPayload) -> TaskResponse:
            """
            Trigger any Celery task by name.

            This endpoint allows triggering any task in the cluster,
            not just tasks registered in this application.

            Useful for:
            - Triggering tasks from other applications
            - Dynamic task invocation
            - Testing and debugging

            Note: queue is required - you must specify which queue to send the task to.
            """
            # Build send_task options - queue is required in GenericTaskPayload
            send_options: dict[str, Any] = {
                "args": payload.args,
                "kwargs": payload.kwargs,
                "queue": payload.queue,
            }

            # Add optional Celery parameters
            if payload.countdown is not None:
                send_options["countdown"] = payload.countdown
            if payload.eta is not None:
                send_options["eta"] = payload.eta
            if payload.expires is not None:
                send_options["expires"] = payload.expires
            if payload.retry is not None:
                send_options["retry"] = payload.retry
            if payload.retry_policy is not None:
                send_options["retry_policy"] = payload.retry_policy
            if payload.exchange is not None:
                send_options["exchange"] = payload.exchange
            if payload.routing_key is not None:
                send_options["routing_key"] = payload.routing_key
            if payload.priority is not None:
                send_options["priority"] = payload.priority
            if payload.serializer is not None:
                send_options["serializer"] = payload.serializer
            if payload.compression is not None:
                send_options["compression"] = payload.compression
            if payload.headers is not None:
                send_options["headers"] = payload.headers
            if payload.task_id is not None:
                send_options["task_id"] = payload.task_id
            if payload.ignore_result is not None:
                send_options["ignore_result"] = payload.ignore_result
            if payload.time_limit is not None:
                send_options["time_limit"] = payload.time_limit
            if payload.soft_time_limit is not None:
                send_options["soft_time_limit"] = payload.soft_time_limit

            result = self.celery_app.send_task(payload.task_name, **send_options)
            return TaskResponse(task_id=result.id, status="PENDING")

    def get_registered_routes(self) -> list[dict[str, str]]:
        """
        Get a list of all registered routes.

        Returns:
            List of dictionaries containing path and method for each route.
        """
        routes: list[dict[str, str]] = []
        for route in self.fastapi_app.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                path = route.path
                methods = route.methods
                for method in methods:
                    if method != "HEAD":
                        routes.append({"path": path, "method": method})
        return routes
