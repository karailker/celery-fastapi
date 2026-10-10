"""Core functionality for Celery FastAPI."""

import asyncio
import contextlib
import hashlib
import hmac
import inspect
import json
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import datetime
from typing import Any, get_type_hints

from celery import Celery
from celery.result import AsyncResult
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field, ValidationInfo, create_model, field_validator

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


def _validate_name(value: str, field_name: str | None) -> str:
    """Reject empty, control-char or otherwise unsafe task/queue names."""
    if not value or not value.strip():
        raise ValueError("must be a non-empty string")
    if any(ord(c) < 0x20 for c in value):
        raise ValueError("control characters are not allowed")
    if not all(c.isalnum() or c in "._-" for c in value):
        raise ValueError("only alphanumeric, '.', '_', '-' allowed")
    if field_name == "task_name" and len(value) > 255:
        raise ValueError("task_name exceeds 255 character limit")
    return value


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

    @field_validator("task_name", "queue")
    @classmethod
    def _validate_names(cls, value: str, info: ValidationInfo) -> str:
        # Trust boundary: reject control chars / injection attempts.
        return _validate_name(value, info.field_name)


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

    # Pydantic task params: if a parameter is annotated with a BaseModel
    # subclass, use that model as the field type directly so its nested
    # schema mirrors into OpenAPI (and Celery native pydantic aware tasks
    # receive the model instance).
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        # Get type annotation
        param_type = type_hints.get(param_name, Any)

        # Handle var-positional (*args) and var-keyword (**kwargs)
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            field_definitions[param_name] = (
                list[param_type],  # type: ignore[valid-type]
                Field(
                    default_factory=list,
                    description=f"Positional arguments for {param_name}",
                ),
            )
            example_kwargs[param_name] = [1, 2]  # example
            continue
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            field_definitions[param_name] = (
                dict[str, param_type],  # type: ignore[valid-type]
                Field(
                    default_factory=dict,
                    description=f"Keyword arguments for {param_name}",
                ),
            )
            example_kwargs[param_name] = {"k": "v"}  # example
            continue

        # Pydantic task param: annotated BaseModel subclass is used as-is.
        if isinstance(param_type, type) and issubclass(param_type, BaseModel):
            field_definitions[param_name] = (
                param_type,
                Field(description=f"Parameter: {param_name} (model)"),
            )
            continue

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


class BatchTaskItem(BaseModel):
    """A single task to execute as part of a batch."""

    task_name: str = Field(description="Full task name (e.g., 'myapp.tasks.add')")
    queue: str | None = Field(default=None, description="Queue override")
    args: list[Any] = Field(
        default_factory=list, description="Positional arguments for the task"
    )
    kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Keyword arguments for the task"
    )
    countdown: float | None = Field(default=None, description="Seconds to wait")

    @field_validator("task_name", "queue")
    @classmethod
    def _validate_names(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return value
        return _validate_name(value, info.field_name)


class BatchTaskRequest(BaseModel):
    """Payload for batch task execution."""

    tasks: list[BatchTaskItem] = Field(
        description="List of tasks to execute as a group"
    )


class BatchTaskResponse(BaseModel):
    """Response model for batch task submission."""

    group_id: str = Field(description="Group ID for the submitted batch")
    task_ids: list[str] = Field(description="Individual task IDs in the group")
    task_count: int = Field(description="Number of tasks submitted")
    status: str = Field(default="PENDING", description="Group status")


class HealthCheckResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str = Field(description="Overall health status (healthy/unhealthy)")
    celery_app: str = Field(description="Celery application name")
    broker_connected: bool = Field(description="Whether broker connection is active")
    worker_hostname: str | None = Field(
        default=None, description="Target worker hostname"
    )
    worker_online: bool = Field(description="Whether the target worker is online")


class PingResponse(BaseModel):
    """Response model for worker ping endpoint."""

    worker_hostname: str | None = Field(
        default=None, description="Target worker hostname"
    )
    online: bool = Field(description="Whether the worker responded to ping")
    response: dict[str, str] | None = Field(
        default=None, description="Ping response from the worker"
    )


class BaseRateLimitStorage(ABC):
    """Abstract rate-limit hit storage.

    Implementations keep per-client hit timestamps so the limiter can run
    against in-process memory, Redis, or any other backing store.
    """

    @abstractmethod
    def prune(self, key: str, cutoff: float) -> None:
        """Drop hits for ``key`` older than ``cutoff`` (monotonic clock)."""

    @abstractmethod
    def count(self, key: str) -> int:
        """Return number of hits for ``key`` within the current window."""

    @abstractmethod
    def add(self, key: str, now: float) -> None:
        """Record one hit for ``key`` at ``now``."""


class InMemoryRateLimitStorage(BaseRateLimitStorage):
    """Sliding-window hit storage held in-process.

    ponytail: single-process default. For multi-worker deployments swap in a
    shared store (e.g. Redis) via ``BaseRateLimitStorage``.
    """

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def prune(self, key: str, cutoff: float) -> None:
        window = self._hits[key]
        while window and window[0] < cutoff:
            window.popleft()

    def count(self, key: str) -> int:
        return len(self._hits[key])

    def add(self, key: str, now: float) -> None:
        self._hits[key].append(now)


class RedisRateLimitStorage(BaseRateLimitStorage):
    """Rate-limit storage backed by Redis (optional extra).

    Requires the ``redis`` package (installed via ``pip install
    celery-fastapi[redis]``). Uses a sorted set per client key; hits are
    timestamps. Works across multiple uvicorn workers.
    """

    def __init__(self, client: Any, window_seconds: int = 60) -> None:
        self._client = client
        self._window_seconds = window_seconds
        self._key_prefix = "celery_fastapi:ratelimit:"
        self._seq = 0  # disambiguates members with identical timestamps

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) % (2**31)
        return self._seq

    def _zkey(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    def prune(self, key: str, cutoff: float) -> None:
        zkey = self._zkey(key)
        # cutoff is monotonic; Redis ZSET scores use wall clock, so we
        # approximate by storing monotonic timestamps as scores.
        self._client.zremrangebyscore(zkey, 0, cutoff)

    def count(self, key: str) -> int:
        zkey = self._zkey(key)
        cutoff = time.monotonic() - self._window_seconds
        self.prune(key, cutoff)
        return int(self._client.zcard(zkey))

    def add(self, key: str, now: float) -> None:
        self._client.zadd(self._zkey(key), {f"{now}:{key}:{self._next_seq()}": now})


class RateLimiter:
    """Sliding-window rate limiter backed by a pluggable storage.

    When the limit is exceeded, `check` raises HTTP 429. Storage defaults to
    in-memory; pass a shared storage to coordinate across processes.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int = 60,
        storage: BaseRateLimitStorage | None = None,
    ) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._storage = storage or InMemoryRateLimitStorage()
        # Sync endpoints run in a threadpool; make prune/count/add atomic.
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Record a hit for ``key``; raise HTTPException(429) if over limit."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            self._storage.prune(key, cutoff)

            if self._storage.count(key) >= self.limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: {self.limit} requests per {self.window_seconds}s",
                )

            self._storage.add(key, now)


class Metrics:
    """Tiny dependency-free Prometheus text-format counters."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, str], int] = defaultdict(int)
        self._lock = threading.Lock()

    def inc(self, metric: str, task: str = "") -> None:
        with self._lock:
            self._counters[(metric, task)] += 1

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def render(self, gauges: dict[str, float]) -> str:
        helps = {
            "tasks_submitted_total": "Tasks dispatched through the API",
            "dispatch_errors_total": "Task dispatches that raised an error",
            "rate_limited_total": "Requests rejected by the rate limiter",
        }
        with self._lock:
            items = sorted(self._counters.items())
        lines: list[str] = []
        for metric, text in helps.items():
            name = f"celery_fastapi_{metric}"
            lines += [f"# HELP {name} {text}", f"# TYPE {name} counter"]
            for (m, task), value in items:
                if m != metric:
                    continue
                label = f'{{task="{self._escape(task)}"}}' if task else ""
                lines.append(f"{name}{label} {value}")
        for gauge, gauge_value in sorted(gauges.items()):
            name = f"celery_fastapi_{gauge}"
            lines += [f"# TYPE {name} gauge", f"{name} {gauge_value}"]
        return "\n".join(lines) + "\n"


class IdempotencyStore:
    """In-memory ``Idempotency-Key`` store (best effort, single process)."""

    def __init__(self, ttl: float = 86400.0, max_items: int = 10000) -> None:
        self.ttl = ttl
        self.max_items = max_items
        self._items: dict[str, tuple[float, str, TaskResponse]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def fingerprint(*parts: str) -> str:
        return hashlib.sha256("\x00".join(parts).encode()).hexdigest()

    def lookup(self, key: str, fingerprint: str) -> "TaskResponse | None":
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(key)
            if entry is None or entry[0] < now:
                return None
            if entry[1] != fingerprint:
                raise HTTPException(
                    status_code=409,
                    detail="Idempotency-Key was already used with a different request",
                )
            return entry[2]

    def save(self, key: str, fingerprint: str, response: "TaskResponse") -> None:
        now = time.monotonic()
        with self._lock:
            self._items[key] = (now + self.ttl, fingerprint, response)
            if len(self._items) > self.max_items:
                for old in sorted(self._items, key=lambda k: self._items[k][0])[
                    : len(self._items) - self.max_items
                ]:
                    del self._items[old]


class _RouteGroup:
    """Registers routes directly on the app with shared dependencies.

    Used instead of ``APIRouter`` + ``include_router`` because recent FastAPI
    versions wrap included routers, hiding individual routes from
    ``app.routes`` (and from ``get_registered_routes``).
    """

    def __init__(
        self, app: FastAPI, dependencies: list[Any], enabled: bool = True
    ) -> None:
        self._app = app
        self._dependencies = dependencies
        self._enabled = enabled

    def _decorator(self, method: str, path: str, **kwargs: Any) -> Callable[..., Any]:
        if not self._enabled:
            return lambda func: func
        kwargs.setdefault("dependencies", self._dependencies)
        decorator: Callable[..., Any] = getattr(self._app, method)(path, **kwargs)
        return decorator

    def get(self, path: str, **kwargs: Any) -> Callable[..., Any]:
        return self._decorator("get", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Callable[..., Any]:
        return self._decorator("post", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Callable[..., Any]:
        return self._decorator("delete", path, **kwargs)


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
        rate_limit: int | None = None,
        rate_limit_storage: BaseRateLimitStorage | None = None,
        middleware: list[Callable] | None = None,
        dependencies: list[Callable[..., Any]] | None = None,
        exclude: set[str] | None = None,
        name_mapping: dict[str, str] | None = None,
        pre_hooks: list[Callable] | None = None,
        post_hooks: list[Callable] | None = None,
        error_mapping: dict[type[Exception], int] | None = None,
        enable_admin_endpoints: bool = False,
        api_key: str | None = None,
        api_key_header: str = "X-API-Key",
        enable_metrics: bool = False,
        enable_mcp: bool = False,
        enable_tracing: bool = False,
        idempotency_ttl: float = 86400.0,
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
            rate_limit: Optional maximum number of requests per minute per client.
                        If set, requests exceeding the limit get HTTP 429.
            rate_limit_storage: Pluggable storage for rate-limit hits (defaults to
                        in-memory). Pass a shared store for multi-worker setups.
            middleware: ASGI HTTP middleware callables to install on the FastAPI app.
            dependencies: FastAPI ``Depends`` providers applied to every HTTP
                        endpoint except ``/healthz`` and ``/ping``.
            exclude: Task names to hide from the API.
            name_mapping: Maps internal task names to public names shown in the API.
            pre_hooks: Callables run before task dispatch; receive the payload.
            post_hooks: Callables run after task dispatch; receive task id and result.
            error_mapping: Maps exception types to HTTP status codes for error responses.
            enable_admin_endpoints: Expose the destructive / unrestricted endpoints
                        (``/purge``, ``/trigger``, task revocation). Off by default.
            api_key: If set, every endpoint except ``/healthz`` and ``/ping`` requires
                        this key (compared in constant time).
            api_key_header: Header carrying the API key (default ``X-API-Key``).
                        WebSockets also accept an ``api_key`` query parameter.
            enable_metrics: Expose Prometheus text metrics at ``/metrics``.
            enable_mcp: Expose tasks as MCP tools at ``/mcp`` (experimental).
            enable_tracing: Wrap dispatches in OpenTelemetry spans (requires
                        ``opentelemetry-api``).
            idempotency_ttl: Seconds an ``Idempotency-Key`` is remembered.
        """
        self.celery_app = celery_app
        self.fastapi_app = fastapi_app or FastAPI()
        self.prefix = prefix.rstrip("/")
        self.include_status_endpoints = include_status_endpoints
        self.task_filter = task_filter or (lambda name: not name.startswith("celery."))
        self.rate_limiter = (
            RateLimiter(rate_limit, storage=rate_limit_storage) if rate_limit else None
        )
        self.middleware = middleware or []
        self.dependencies = dependencies or []
        self.exclude = exclude or set()
        self.name_mapping = name_mapping or {}
        self.pre_hooks = pre_hooks or []
        self.post_hooks = post_hooks or []
        self.error_mapping = error_mapping or {}
        self.enable_admin_endpoints = enable_admin_endpoints
        self.api_key = api_key
        self.api_key_header = api_key_header
        self.enable_metrics = enable_metrics
        self.enable_mcp = enable_mcp
        self.enable_tracing = enable_tracing
        self.metrics = Metrics()
        self.idempotency = IdempotencyStore(idempotency_ttl)
        self._task_models: dict[str, type[BaseModel]] = {}
        self._tracer: Any = None
        if enable_tracing:
            try:
                from opentelemetry import trace
            except ImportError as exc:
                raise ImportError(
                    "enable_tracing requires opentelemetry-api. "
                    "Install with: pip install celery-fastapi[otel]"
                ) from exc
            self._tracer = trace.get_tracer("celery_fastapi")
        self._registered = False

        # Store the registered task names from THIS app only
        self._app_task_names: set[str] = set()
        for name in self.celery_app.tasks:
            if name not in self.exclude and self.task_filter(name):
                self._app_task_names.add(name)

    def _key_matches(self, supplied: str | None) -> bool:
        if self.api_key is None:
            return True
        return supplied is not None and hmac.compare_digest(
            supplied.encode(), self.api_key.encode()
        )

    def _protected_deps(self) -> list[Any]:
        """Dependencies applied to every protected HTTP endpoint."""
        deps: list[Any] = []
        if self.api_key is not None:
            header_name = self.api_key_header

            def require_api_key(request: Request) -> None:
                if not self._key_matches(request.headers.get(header_name)):
                    raise HTTPException(
                        status_code=401, detail="Invalid or missing API key"
                    )

            deps.append(Depends(require_api_key))
        deps.extend(Depends(d) for d in self.dependencies)
        return deps

    def _check_rate_limit(self, request: Request) -> None:
        """Apply the per-client rate limit (no-op when not configured)."""
        if self.rate_limiter is not None:
            client_ip = request.client.host if request.client else "unknown"
            try:
                self.rate_limiter.check(client_ip)
            except HTTPException:
                self.metrics.inc("rate_limited_total")
                raise

    def _task_snapshot(self, task_id: str) -> dict[str, Any]:
        """Current state of a task as a JSON-friendly frame (blocking I/O)."""
        result = AsyncResult(task_id, app=self.celery_app)
        frame: dict[str, Any] = {
            "task_id": task_id,
            "state": result.state,
            "ready": result.ready(),
        }
        if frame["ready"]:
            if result.failed():
                frame["error"] = str(result.traceback or "task failed")
            else:
                frame["result"] = result.result
        return frame

    def _dispatch(self, task_name: str, send_options: dict[str, Any]) -> Any:
        """Send a task, recording metrics and (optionally) a tracing span."""
        span: Any = contextlib.nullcontext()
        if self._tracer is not None:
            span = self._tracer.start_as_current_span(
                "celery_fastapi.send_task",
                attributes={
                    "celery.task_name": task_name,
                    "celery.queue": str(send_options.get("queue", "")),
                },
            )
        with span:
            try:
                result = self.celery_app.send_task(task_name, **send_options)
            except Exception:
                self.metrics.inc("dispatch_errors_total", task_name)
                raise
        self.metrics.inc("tasks_submitted_total", task_name)
        return result

    def _idempotent_lookup(
        self, request: Request, response: Response, scope: str, fingerprint: str
    ) -> "TaskResponse | None":
        key = request.headers.get("Idempotency-Key")
        if not key:
            return None
        found = self.idempotency.lookup(
            f"{scope}:{key}", IdempotencyStore.fingerprint(scope, fingerprint)
        )
        if found is not None:
            response.headers["Idempotent-Replayed"] = "true"
        return found

    def _idempotent_save(
        self, request: Request, scope: str, fingerprint: str, result: "TaskResponse"
    ) -> None:
        key = request.headers.get("Idempotency-Key")
        if key:
            self.idempotency.save(
                f"{scope}:{key}",
                IdempotencyStore.fingerprint(scope, fingerprint),
                result,
            )

    def _build_send_options(self, payload: Any, queue: str) -> dict[str, Any]:
        """Translate a task payload model into ``send_task`` keyword arguments."""
        celery_option_names = set(CELERY_OPTIONS_FIELDS.keys())
        task_kwargs: dict[str, Any] = {}

        # Access model_fields from the class, not the instance (Pydantic V2.11+)
        for field_name in type(payload).model_fields:
            if field_name not in celery_option_names:
                value = getattr(payload, field_name, None)
                # Pydantic task params arrive as model instances; flatten to a
                # plain dict so the broker serializer (e.g. json) can encode it.
                if isinstance(value, BaseModel):
                    value = value.model_dump()
                if value is not None:
                    task_kwargs[field_name] = value

        send_options: dict[str, Any] = {"args": [], "kwargs": {}, "queue": queue}

        # VAR_POSITIONAL (*args) must go into send_options["args"], not kwargs
        var_positional_name = None
        for field_name, value in task_kwargs.items():
            if field_name == "args" and isinstance(value, list):
                var_positional_name = field_name
            elif field_name == "kwargs" and isinstance(value, dict):
                send_options["kwargs"] = value
            elif field_name not in ("args", "kwargs"):
                send_options["kwargs"][field_name] = value

        if var_positional_name is not None:
            send_options["args"] = task_kwargs[var_positional_name]

        for opt_name in celery_option_names:
            value = getattr(payload, opt_name, None)
            if value is not None and opt_name != "queue":  # queue handled above
                send_options[opt_name] = value
        return send_options

    def register_routes(self) -> FastAPI:
        """
        Register all Celery task routes on the FastAPI application.

        Returns:
            The FastAPI application with registered routes.
        """
        if self._registered:
            return self.fastapi_app

        # Install user-supplied ASGI http middleware before routes are added.
        for middleware_fn in self.middleware:
            self.fastapi_app.middleware("http")(middleware_fn)

        # Custom exception mapping: Celery exception type -> HTTP status code.
        if self.error_mapping:
            error_map = self.error_mapping.copy()

            @self.fastapi_app.exception_handler(Exception)
            async def _error_mapper(_request: Request, exc: Exception) -> JSONResponse:
                code = error_map.get(type(exc), 500)
                return JSONResponse(status_code=code, content={"detail": str(exc)})

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
            if name in self.exclude or not self.task_filter(name):
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
        self._task_models[task_name] = PayloadModel

        # Create the endpoint handler
        def run_task(
            request: Request,
            response: Response,
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
            self._check_rate_limit(request)

            # Determine actual task name and queue
            actual_task_name = task_name_override or task_name
            # Overrides may only redirect to another task this API exposes;
            # otherwise any task in the cluster could be run from here.
            if (
                actual_task_name != task_name
                and actual_task_name not in self._app_task_names
            ):
                raise HTTPException(
                    status_code=404,
                    detail=f"Task '{actual_task_name}' is not exposed by this API",
                )
            if queue_override is not None:
                try:
                    _validate_name(queue_override, "queue")
                except ValueError as exc:
                    raise HTTPException(
                        status_code=422, detail=f"Invalid _queue: {exc}"
                    ) from exc
            actual_queue = (
                queue_override or getattr(payload, "queue", None) or queue_name
            )

            send_options = self._build_send_options(payload, actual_queue)

            fingerprint = f"{actual_queue}:{payload.model_dump_json()}"  # type: ignore[attr-defined]
            replay = self._idempotent_lookup(
                request, response, actual_task_name, fingerprint
            )
            if replay is not None:
                return replay

            # Pre-hooks: run before dispatch (e.g. auth, audit). Raise -> 500.
            for hook in self.pre_hooks:
                hook(payload)

            try:
                result = self._dispatch(actual_task_name, send_options)
            except Exception as exc:  # noqa: BLE001
                status = self.error_mapping.get(type(exc), 500)
                raise HTTPException(status_code=status, detail=str(exc)) from exc

            task_response = TaskResponse(task_id=result.id, status="PENDING")
            self._idempotent_save(request, actual_task_name, fingerprint, task_response)

            # Post-hooks: run after dispatch (e.g. notify, log).
            for hook in self.post_hooks:
                hook(task_response)

            return task_response

        # Set a descriptive name for the endpoint
        run_task.__name__ = f"run_{task_name.replace('.', '_')}"
        run_task.__doc__ = f"Execute '{task_name}' task. Default queue: '{queue_name}'."

        # API key + user dependencies (e.g. auth provider) as FastAPI Depends.
        deps = self._protected_deps()

        self.fastapi_app.post(
            route_path,
            response_model=TaskResponse,
            tags=["tasks"],
            dependencies=deps,
            summary=f"Run {task_name}",
            description=f"Submit '{task_name}' task for async execution.\n\nDefault queue: `{queue_name}`\n\nUse `_task_name` and `_queue` query params to override.",
        )(run_task)

    def _register_status_endpoints(self) -> None:
        """Register task status, listing, and control endpoints."""
        # Protected: API key + user dependencies. Admin: protected + opt-in.
        # Public: probes only (/healthz, /ping), so orchestrators can reach them.
        router = _RouteGroup(self.fastapi_app, self._protected_deps())
        admin = _RouteGroup(
            self.fastapi_app, self._protected_deps(), self.enable_admin_endpoints
        )
        public = _RouteGroup(self.fastapi_app, [])

        @router.get(
            f"{self.prefix}/tasks/{{task_id}}",
            response_model=TaskStatusResponse,
            tags=["task-status"],
            summary="Get task status",
        )
        def get_task_status(task_id: str) -> TaskStatusResponse:
            """
            Get the status of a specific task by its ID.

            Returns detailed information including state, result, and traceback.

            Raises:
                Nothing: unknown/not-started tasks report state PENDING.
            """
            result = AsyncResult(task_id, app=self.celery_app)

            # Celery reports PENDING for unknown *and* not-yet-started tasks;
            # treat both as PENDING so freshly submitted tasks are queryable.
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

        @admin.delete(
            f"{self.prefix}/tasks/{{task_id}}",
            tags=["task-status"],
            summary="Revoke a task",
        )
        def revoke_task(
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

        @router.get(
            f"{self.prefix}/tasks/{{task_id}}/result",
            tags=["task-status"],
            summary="Get task result",
        )
        def get_task_result(task_id: str, timeout: float | None = None) -> Any:
            """
            Get the result of a completed task.

            Args:
                task_id: The task ID.
                timeout: Optional timeout in seconds to wait for result.

            Returns:
                The task result.

            Raises:
                HTTPException: 202 if not ready (including PENDING), 500 on failure.
            """
            result = AsyncResult(task_id, app=self.celery_app)

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

        @self.fastapi_app.websocket(f"{self.prefix}/tasks/{{task_id}}/ws")
        async def stream_task_status(websocket: WebSocket, task_id: str) -> None:
            """
            Stream task status updates via WebSocket.

            Polls the task state every 0.5s and sends JSON frames until the
            task reaches a terminal state (SUCCESS/FAILURE/REVOKED), then closes.

            ponytail: polling-based. For high-throughput streams, replace with
            Celery events (celery_app.events.Receiver) or Redis pub/sub.
            """
            supplied = websocket.headers.get(self.api_key_header) or (
                websocket.query_params.get("api_key")
            )
            if not self._key_matches(supplied):
                await websocket.close(code=1008)
                return
            await websocket.accept()
            try:
                while True:
                    # Backend lookups are blocking I/O; keep them off the loop.
                    frame = await asyncio.to_thread(self._task_snapshot, task_id)
                    await websocket.send_json(frame)
                    if frame["ready"]:
                        break
                    await asyncio.sleep(0.5)
            except WebSocketDisconnect:
                pass

        @router.get(
            f"{self.prefix}/tasks",
            response_model=TaskListResponse,
            tags=["task-status"],
            summary="List all tasks",
        )
        def list_all_tasks(
            worker: str | None = Query(
                default=None, description="Only tasks on this worker"
            ),
            name: str | None = Query(
                default=None, description="Only tasks whose name contains this text"
            ),
            limit: int | None = Query(
                default=None, ge=1, le=1000, description="Max tasks per worker list"
            ),
            offset: int = Query(default=0, ge=0, description="Skip this many tasks"),
        ) -> TaskListResponse:
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
                for worker_name, task_list in tasks_by_worker.items():
                    if worker is not None and worker_name != worker:
                        continue
                    filtered_list = [
                        t
                        for t in task_list
                        if t.get("name") in self._app_task_names
                        and (name is None or name in str(t.get("name")))
                    ]
                    page = filtered_list[
                        offset : None if limit is None else offset + limit
                    ]
                    if page:
                        filtered[worker_name] = page
                return filtered

            return TaskListResponse(
                active=filter_tasks(inspector.active()),
                scheduled=filter_tasks(inspector.scheduled()),
                reserved=filter_tasks(inspector.reserved()),
                revoked={
                    w: ids
                    for w, ids in (inspector.revoked() or {}).items()
                    if worker is None or w == worker
                },  # Revoked is just task IDs, can't filter by task name
            )

        @router.get(
            f"{self.prefix}/workers",
            tags=["workers"],
            summary="List workers",
        )
        def list_workers() -> dict[str, Any]:
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

        @router.get(
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
                    # Apply optional name mapping for public-facing names.
                    public_name = self.name_mapping.get(name, name)
                    tasks_info.append(
                        {
                            "name": public_name,
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

        @router.post(
            f"{self.prefix}/tasks/chain",
            response_model=BatchTaskResponse,
            tags=["tasks"],
            summary="Execute tasks in a chain",
            description="Execute multiple Celery tasks sequentially. Tasks are executed one after another, with the result of one task passed to the next.",
        )
        def chain_tasks(
            request: Request, payload: BatchTaskRequest
        ) -> BatchTaskResponse:
            """Execute tasks in a chain.

            Args:
                payload: BatchTaskRequest containing a list of tasks.

            Returns:
                BatchTaskResponse with group ID and individual task IDs.
            """
            from celery import chain

            self._check_rate_limit(request)

            if not payload.tasks:
                raise HTTPException(status_code=422, detail="No tasks provided")

            signatures = []
            for item in payload.tasks:
                if not item.task_name:
                    raise HTTPException(
                        status_code=422, detail="task_name is required for each task"
                    )

                if item.task_name not in self._app_task_names:
                    raise HTTPException(
                        status_code=404,
                        detail=f"task '{item.task_name}' is not registered in this app",
                    )

                if item.task_name not in self._app_task_names:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Task '{item.task_name}' is not exposed by this API",
                    )
                sig = self.celery_app.signature(
                    item.task_name,
                    args=item.args,
                    kwargs=item.kwargs,
                    queue=item.queue,
                )
                signatures.append(sig)

            job = chain(*signatures)
            result = job.apply_async()
            task_ids = [r.id for r in result.children or []]
            for item in payload.tasks:
                self.metrics.inc("tasks_submitted_total", item.task_name)

            return BatchTaskResponse(
                group_id=result.id,
                task_ids=task_ids,
                task_count=len(payload.tasks),
                status="PENDING",
            )

        @router.post(
            f"{self.prefix}/tasks/chord",
            response_model=BatchTaskResponse,
            tags=["tasks"],
            summary="Execute tasks in a chord",
            description="Execute multiple Celery tasks as a group, followed by a callback task upon completion of all group tasks.",
        )
        def chord_tasks(request: Request, payload: dict[str, Any]) -> BatchTaskResponse:
            """Execute tasks in a chord.

            Args:
                payload: Dictionary containing 'header' (list of BatchTaskItem)
                         and 'callback' (task name string).

            Returns:
                BatchTaskResponse with group ID and individual task IDs.
            """
            from celery import chord

            self._check_rate_limit(request)

            header_tasks = payload.get("header")
            callback_task_name = payload.get("callback")

            if not header_tasks or not callback_task_name:
                raise HTTPException(
                    status_code=422,
                    detail="'header' and 'callback' are required for chord",
                )

            if callback_task_name not in self._app_task_names:
                raise HTTPException(
                    status_code=404,
                    detail=f"task '{callback_task_name}' is not registered in this app",
                )

            header_signatures = []
            for item in header_tasks:
                if not item.get("task_name"):
                    raise HTTPException(
                        status_code=422,
                        detail="task_name is required for each task in header",
                    )

                if item["task_name"] not in self._app_task_names:
                    raise HTTPException(
                        status_code=404,
                        detail=f"task '{item['task_name']}' is not registered in this app",
                    )

                sig = self.celery_app.signature(
                    item["task_name"],
                    args=item.get("args", []),
                    kwargs=item.get("kwargs", {}),
                    queue=item.get("queue"),
                )
                header_signatures.append(sig)

            callback_sig = self.celery_app.signature(callback_task_name)

            # chord syntax: chord(header)(callback).apply_async()
            job = chord(header_signatures, body=callback_sig)
            result = job.apply_async()

            # For chord, the header group task IDs are available via result.parent.children
            # if we have the parent. But apply_async returns the callback result.
            task_ids = []
            if result.parent and result.parent.children:
                task_ids = [r.id for r in result.parent.children]

            return BatchTaskResponse(
                group_id=result.id,
                task_ids=task_ids,
                task_count=len(header_tasks),
                status="PENDING",
            )

        @router.get(
            f"{self.prefix}/tasks/{{task_id}}/events",
            tags=["task-status"],
            summary="Stream task status (Server-Sent Events)",
        )
        async def stream_task_events(
            task_id: str, request: Request
        ) -> StreamingResponse:
            """
            Stream task status as Server-Sent Events.

            Emits an ``status`` event every 0.5s until the task is ready. Unlike
            the WebSocket endpoint this works through plain HTTP proxies and
            ``EventSource`` clients.
            """

            async def events() -> Any:
                while True:
                    if await request.is_disconnected():
                        break
                    frame = await asyncio.to_thread(self._task_snapshot, task_id)
                    yield f"event: status\ndata: {json.dumps(frame, default=str)}\n\n"
                    if frame["ready"]:
                        break
                    await asyncio.sleep(0.5)

            return StreamingResponse(
                events(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        @router.get(
            f"{self.prefix}/schedules",
            tags=["schedules"],
            summary="List Celery Beat schedules (read-only)",
        )
        def list_schedules() -> dict[str, Any]:
            """List ``beat_schedule`` entries that target tasks exposed by this API."""
            schedule = self.celery_app.conf.beat_schedule or {}
            entries: list[dict[str, Any]] = []
            for entry_name, entry in sorted(schedule.items()):
                task = entry.get("task")
                if task not in self._app_task_names:
                    continue
                entries.append(
                    {
                        "name": entry_name,
                        "task": self.name_mapping.get(task, task),
                        "schedule": str(entry.get("schedule")),
                        "args": list(entry.get("args") or []),
                        "kwargs": dict(entry.get("kwargs") or {}),
                        "options": dict(entry.get("options") or {}),
                    }
                )
            return {"count": len(entries), "schedules": entries}

        if self.enable_metrics:

            @router.get(
                f"{self.prefix}/metrics",
                tags=["observability"],
                summary="Prometheus metrics",
                response_class=PlainTextResponse,
            )
            def metrics_endpoint() -> PlainTextResponse:
                """Prometheus text-format metrics for this API and its broker."""
                gauges: dict[str, float] = {"broker_up": 0.0}
                try:
                    ping = self.celery_app.control.inspect(timeout=1.0).ping() or {}
                    gauges["broker_up"] = 1.0
                    gauges["workers_online"] = float(len(ping))
                except Exception:  # noqa: BLE001
                    pass
                return PlainTextResponse(
                    self.metrics.render(gauges),
                    media_type="text/plain; version=0.0.4; charset=utf-8",
                )

        if self.enable_mcp:
            self._register_mcp(router)

        def _find_local_worker() -> str | None:
            """
            Find the Celery worker running on the same host.

            Celery worker hostnames follow the pattern: prefix@hostname
            where prefix can be any format (e.g., celery, appname_uuid, etc.).

            Matching strategy:
            1. CELERY_WORKER_HOSTNAME environment variable (RECOMMENDED)
               Set this to the exact worker name when starting both worker and API
               Example: export CELERY_WORKER_HOSTNAME="celery@worker1"

            2. Hostname matching (works when worker and API share same hostname):
               - Exact match: worker hostname part equals socket.gethostname()
               - Partial match: handles FQDN vs short hostname

            3. Single worker fallback (only when one worker exists for this app)

            Note: When using custom --hostname, always set CELERY_WORKER_HOSTNAME
            to ensure correct worker discovery.

            Examples:
            - Standard: celery@myhost (auto-discovered)
            - Custom: celery@worker1 (needs CELERY_WORKER_HOSTNAME="celery@worker1")
            - UUID: myapp_abc123@myhost (auto-discovered if hostname matches)
            """
            import os
            import socket

            # Strategy 1: Check for explicit environment variable (RECOMMENDED)
            env_worker = os.environ.get("CELERY_WORKER_HOSTNAME")
            if env_worker:
                try:
                    inspector = self.celery_app.control.inspect(timeout=1.0)
                    env_ping_response: dict[str, Any] = inspector.ping() or {}
                    if env_worker in env_ping_response:
                        return str(env_worker)
                    # If env var is set but worker not found, log and continue
                except Exception:  # noqa: BLE001
                    pass

            local_hostname = socket.gethostname()

            try:
                inspector = self.celery_app.control.inspect(timeout=1.0)

                # Get all active workers
                ping_response: dict[str, Any] = inspector.ping() or {}
                if not ping_response:
                    return None

                # Strategy 2: Hostname-based matching
                # First pass: exact hostname match
                for worker_name in ping_response:
                    if "@" in worker_name:
                        _, worker_host = worker_name.rsplit("@", 1)
                        if worker_host == local_hostname:
                            return str(worker_name)
                    elif worker_name == local_hostname:
                        return str(worker_name)

                # Second pass: partial hostname match (FQDN vs short name)
                for worker_name in ping_response:
                    if "@" in worker_name:
                        _, worker_host = worker_name.rsplit("@", 1)
                        if (
                            local_hostname in worker_host
                            or worker_host in local_hostname
                        ):
                            return str(worker_name)

                # Strategy 3: Filter by app tasks and check for single worker
                registered: dict[str, list[str]] = inspector.registered() or {}
                app_workers = []
                for worker_name in ping_response:
                    worker_tasks = registered.get(worker_name, [])
                    if any(task in self._app_task_names for task in worker_tasks):
                        app_workers.append(worker_name)

                # If only one worker has this app's tasks, assume it's local
                if len(app_workers) == 1:
                    return str(app_workers[0])

                # If multiple workers with same tasks exist and hostname doesn't match,
                # we cannot determine which is local without CELERY_WORKER_HOSTNAME
                return None
            except Exception:  # noqa: BLE001
                return None

        @public.get(
            f"{self.prefix}/healthz",
            response_model=HealthCheckResponse,
            tags=["health"],
            summary="Health check",
        )
        def health_check(
            worker: str | None = Query(
                default=None,
                description=(
                    "Explicit worker hostname to check (e.g., 'celery@worker1'). "
                    "If provided, bypasses local worker discovery."
                ),
            ),
        ) -> HealthCheckResponse:
            """
            Check the health of a Celery worker.

            If a `worker` query parameter is provided, checks that specific worker.
            Otherwise, automatically discovers the worker running on the same host by
            matching the system hostname with active Celery worker hostnames.

            Returns:
                Health status including broker connection and worker availability.

            This endpoint is useful for:
            - Kubernetes/Docker health probes (sidecar pattern)
            - Load balancer health checks
            - Monitoring systems
            """
            local_worker = worker  # Use explicit worker if provided
            try:
                broker_connected = True
                if local_worker is None:
                    local_worker = _find_local_worker()
                # When a specific worker is requested, verify it's online via inspection.
                # In environments without active workers, this will be False.
                inspector = self.celery_app.control.inspect(
                    destination=[local_worker] if local_worker else None
                )
                ping_response = inspector.ping() or {}
                worker_online = local_worker in ping_response if local_worker else False

            except Exception:  # noqa: BLE001
                broker_connected = False
                local_worker = None
                worker_online = False

            # Determine overall health status
            status = "healthy" if broker_connected and worker_online else "unhealthy"

            return HealthCheckResponse(
                status=status,
                celery_app=self.celery_app.main,
                broker_connected=broker_connected,
                worker_hostname=local_worker,
                worker_online=worker_online,
            )

        @public.get(
            f"{self.prefix}/ping",
            response_model=PingResponse,
            tags=["health"],
            summary="Ping worker",
        )
        def ping_worker(
            worker: str | None = Query(
                default=None,
                description=(
                    "Explicit worker hostname to ping (e.g., 'celery@worker1'). "
                    "If provided, bypasses local worker discovery."
                ),
            ),
        ) -> PingResponse:
            """
            Ping a Celery worker.

            If a `worker` query parameter is provided, pings that specific worker.
            Otherwise, automatically discovers the local Celery worker by matching
            the system hostname with active Celery worker hostnames.

            Returns:
                Ping response from the discovered or specified worker.

            This endpoint is useful for:
            - Checking specific worker responsiveness
            - Diagnosing connection issues
            - Verifying worker health in containerized deployments
            """
            local_worker = worker  # Use explicit worker if provided
            if not local_worker:
                local_worker = _find_local_worker()

            if not local_worker:
                # No worker found or specified
                return PingResponse(
                    worker_hostname=None,
                    online=False,
                    response=None,
                )

            # Ping the specific worker
            inspector = self.celery_app.control.inspect(destination=[local_worker])
            ping_response = inspector.ping() or {}

            worker_response = ping_response.get(local_worker)

            return PingResponse(
                worker_hostname=local_worker,
                online=worker_response is not None,
                response=worker_response,
            )

        @admin.post(
            f"{self.prefix}/purge",
            tags=["workers"],
            summary="Purge all tasks",
        )
        def purge_tasks() -> dict[str, int]:
            """Purge all pending tasks from the queue."""
            count = self.celery_app.control.purge()
            return {"purged": count or 0}

        @admin.post(
            f"{self.prefix}/trigger",
            response_model=TaskResponse,
            tags=["tasks"],
            summary="Trigger any task",
        )
        def trigger_generic_task(
            request: Request, response: Response, payload: GenericTaskPayload
        ) -> TaskResponse:
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
            self._check_rate_limit(request)

            fingerprint = payload.model_dump_json()
            replay = self._idempotent_lookup(
                request, response, f"trigger:{payload.task_name}", fingerprint
            )
            if replay is not None:
                return replay

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

            result = self._dispatch(payload.task_name, send_options)
            task_response = TaskResponse(task_id=result.id, status="PENDING")
            self._idempotent_save(
                request, f"trigger:{payload.task_name}", fingerprint, task_response
            )
            return task_response

        @router.post(
            f"{self.prefix}/tasks/batch",
            response_model=BatchTaskResponse,
            tags=["tasks"],
            summary="Execute multiple tasks in a group",
        )
        def batch_execute_tasks(
            request: Request,
            payload: BatchTaskRequest,
        ) -> BatchTaskResponse:
            """
            Execute multiple Celery tasks as a single group.

            The tasks are submitted as a Celery group, enabling coordinated
            execution and result collection.

            Returns:
                Group ID, individual task IDs, and count of submitted tasks.
            """
            from celery import group

            self._check_rate_limit(request)

            # Validate: at least one task required
            if not payload.tasks:
                raise HTTPException(status_code=422, detail="No tasks provided")

            # Build Celery signatures for each task
            signatures = []
            for item in payload.tasks:
                if not item.task_name:
                    raise HTTPException(
                        status_code=422, detail="task_name is required for each task"
                    )
                if item.task_name not in self._app_task_names:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Task '{item.task_name}' is not exposed by this API",
                    )
                sig = self.celery_app.signature(
                    item.task_name,
                    args=item.args,
                    kwargs=item.kwargs,
                    queue=item.queue,
                )
                signatures.append(sig)

            # Submit the group
            job = group(*signatures)
            result = job.apply_async()

            task_ids = [r.id for r in result.children or []]
            for item in payload.tasks:
                self.metrics.inc("tasks_submitted_total", item.task_name)

            return BatchTaskResponse(
                group_id=result.id,
                task_ids=task_ids,
                task_count=len(payload.tasks),
                status="PENDING",
            )

        @admin.post(
            f"{self.prefix}/tasks/batch/revoke",
            summary="Revoke multiple tasks",
        )
        def batch_revoke_tasks(
            payload: dict[str, list[str]],
        ) -> dict[str, Any]:
            """
            Revoke multiple tasks by their task IDs.

            Task IDs should be provided in the `task_ids` field.
            """
            task_ids = payload.get("task_ids", [])
            if not task_ids:
                raise HTTPException(status_code=422, detail="task_ids is required")

            for task_id in task_ids:
                self.celery_app.control.revoke(task_id)

            return {"status": "revoked", "task_ids": task_ids, "count": len(task_ids)}

    def _mcp_tools(self) -> dict[str, tuple[str, dict[str, Any]]]:
        """Map public tool name -> (internal task name, JSON input schema)."""
        option_names = set(CELERY_OPTIONS_FIELDS)
        tools: dict[str, tuple[str, dict[str, Any]]] = {}
        for task_name in sorted(self._app_task_names):
            model = self._task_models.get(task_name)
            if model is None:
                continue
            schema = model.model_json_schema()
            props = {
                k: v
                for k, v in schema.get("properties", {}).items()
                if k not in option_names
            }
            schema["properties"] = props
            schema["required"] = [r for r in schema.get("required", []) if r in props]
            schema.pop("title", None)
            tools[self.name_mapping.get(task_name, task_name)] = (task_name, schema)
        return tools

    def _register_mcp(self, router: _RouteGroup) -> None:
        """Expose tasks as MCP tools over a minimal JSON-RPC HTTP endpoint."""
        status_tool = "get_task_status"

        @router.post(
            f"{self.prefix}/mcp",
            tags=["mcp"],
            summary="Model Context Protocol endpoint (experimental)",
        )
        def mcp_endpoint(request: Request, body: dict[str, Any]) -> Response:
            """Minimal MCP server: ``initialize``, ``tools/list`` and ``tools/call``."""
            method = body.get("method")
            rpc_id = body.get("id")
            if rpc_id is None:  # notification (e.g. notifications/initialized)
                return Response(status_code=202)

            def reply(result: Any) -> JSONResponse:
                return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})

            def error(code: int, message: str) -> JSONResponse:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {"code": code, "message": message},
                    }
                )

            def tool_result(payload: Any, is_error: bool = False) -> JSONResponse:
                return reply(
                    {
                        "content": [
                            {"type": "text", "text": json.dumps(payload, default=str)}
                        ],
                        "isError": is_error,
                    }
                )

            params = body.get("params") or {}
            if method == "initialize":
                return reply(
                    {
                        "protocolVersion": params.get("protocolVersion", "2025-03-26"),
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "celery-fastapi", "version": "0.1.6"},
                    }
                )
            if method == "ping":
                return reply({})

            tools = self._mcp_tools()
            if method == "tools/list":
                listed = [
                    {
                        "name": public,
                        "description": f"Submit Celery task '{internal}' (async).",
                        "inputSchema": schema,
                    }
                    for public, (internal, schema) in tools.items()
                ]
                listed.append(
                    {
                        "name": status_tool,
                        "description": "Get the state and result of a submitted task.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"task_id": {"type": "string"}},
                            "required": ["task_id"],
                        },
                    }
                )
                return reply({"tools": listed})

            if method == "tools/call":
                tool = params.get("name")
                arguments = params.get("arguments") or {}
                if tool == status_tool:
                    task_id = arguments.get("task_id")
                    if not isinstance(task_id, str) or not task_id:
                        return tool_result({"error": "task_id is required"}, True)
                    return tool_result(self._task_snapshot(task_id))
                if tool not in tools:
                    return error(-32602, f"Unknown tool: {tool}")
                self._check_rate_limit(request)
                internal, _schema = tools[tool]
                model = self._task_models[internal]
                try:
                    payload = model.model_validate(arguments)
                except Exception as exc:  # noqa: BLE001
                    return tool_result({"error": str(exc)}, True)
                queue = getattr(self.celery_app.tasks.get(internal), "queue", None) or (
                    self.celery_app.conf.task_default_queue or "celery"
                )
                send_options = self._build_send_options(payload, queue)
                for hook in self.pre_hooks:
                    hook(payload)
                try:
                    result = self._dispatch(internal, send_options)
                except Exception as exc:  # noqa: BLE001
                    return tool_result({"error": str(exc)}, True)
                task_response = TaskResponse(task_id=result.id, status="PENDING")
                for hook in self.post_hooks:
                    hook(task_response)
                return tool_result(task_response.model_dump())

            return error(-32601, f"Method not found: {method}")

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
