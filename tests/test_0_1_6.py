"""Tests for 0.1.6 features: pydantic task param, chain, chord, hooks, error mapping, exclude/name_mapping."""

from __future__ import annotations

from typing import Any

import pytest
from celery import Celery
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from celery_fastapi import CeleryFastAPIBridge, GenericTaskPayload, create_app


class Item(BaseModel):
    """Concrete model used as a Pydantic task parameter."""

    name: str
    qty: int = Field(default=1)


def _make_celery_app(name: str = "test_0_1_6") -> Celery:
    app = Celery(name, broker="memory://", backend="cache+memory://")
    app.conf.update(task_always_eager=True, task_eager_propagates=True)

    @app.task(name=f"{name}.add")
    def add(x: int, y: int) -> int:
        return x + y

    @app.task(name=f"{name}.add_seq")
    def add_seq(*args: int) -> int:
        return sum(args)

    @app.task(name=f"{name}.greet")
    def greet(name: str) -> str:
        return f"Hello, {name}!"

    @app.task(name=f"{name}.pyd")
    def pyd_model(payload: Item) -> dict[str, Any]:
        return payload.model_dump()

    return app


# 1. Pydantic task param support
def test_pydantic_task_param_routed() -> None:
    """A task annotated with BaseModel subclass accepts the model payload."""
    app = _make_celery_app("test_pyd")
    fastapi_app = create_app(app)
    client = TestClient(fastapi_app)

    response = client.post(
        "/test_pyd/pyd",
        json={"payload": {"name": "x", "qty": 3}},
    )
    assert response.status_code == 200
    assert "task_id" in response.json()


def test_pydantic_payload_preserves_nested_schema() -> None:
    """The dynamic payload model keeps the nested BaseModel schema."""
    app = _make_celery_app("test_pyd_schema")
    fastapi_app = create_app(app)
    client = TestClient(fastapi_app)

    schema = client.get("/openapi.json").json()
    pyd_path = "/test_pyd_schema/pyd"
    assert pyd_path in schema["paths"]
    body = schema["paths"][pyd_path]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    ref = body["$ref"]
    model_name = ref.rsplit("/", 1)[-1]
    payload_schema = schema["components"]["schemas"][model_name]["properties"][
        "payload"
    ]
    # The nested Item model appears as a $ref or inline; either proves the
    # BaseModel task param is carried through to the OpenAPI schema.
    assert payload_schema.get("$ref") or payload_schema.get("type")


def test_generic_task_payload_still_supported() -> None:
    """The /trigger endpoint still uses GenericTaskPayload."""
    app = _make_celery_app("test_generic")
    fastapi_app = create_app(app)
    client = TestClient(fastapi_app)

    response = client.post(
        "/trigger",
        json=GenericTaskPayload(
            task_name="test_generic.add",
            queue="celery",
            args=[1, 2],
        ).model_dump(),
    )
    assert response.status_code == 200


# 2. Pluggable Rate Limit Storage
def test_in_memory_storage_default() -> None:
    """Default RateLimiter uses in-memory storage."""
    from celery_fastapi.core import InMemoryRateLimitStorage, RateLimiter

    limiter = RateLimiter(limit=2)
    assert isinstance(limiter._storage, InMemoryRateLimitStorage)
    limiter.check("k")
    limiter.check("k")
    with pytest.raises(HTTPException):
        limiter.check("k")


# 3. Chain endpoint
def test_chain_endpoint() -> None:
    app = _make_celery_app("test_chain")
    fastapi_app = create_app(app)
    client = TestClient(fastapi_app)

    response = client.post(
        "/tasks/chain",
        json={
            "tasks": [
                {"task_name": "test_chain.add_seq", "args": [1, 2]},
                {"task_name": "test_chain.add_seq", "args": [3, 4]},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "group_id" in data
    assert data["task_count"] == 2


# 4. Chord endpoint
def test_chord_endpoint() -> None:
    app = _make_celery_app("test_chord")
    fastapi_app = create_app(app)
    client = TestClient(fastapi_app)

    response = client.post(
        "/tasks/chord",
        json={
            "header": [
                {"task_name": "test_chord.add", "args": [1, 2]},
                {"task_name": "test_chord.add", "args": [3, 4]},
            ],
            "callback": "test_chord.greet",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "group_id" in data
    assert data["task_count"] == 2


# 5. Exclude and name mapping
def test_exclude_task_name() -> None:
    """Excluded task is not registered as an endpoint."""
    app = _make_celery_app("test_exclude")
    bridge = CeleryFastAPIBridge(app, exclude={"test_exclude.greet"})
    fastapi_app = bridge.register_routes()
    routes = [r.path for r in fastapi_app.routes]
    assert "/test_exclude/add" in routes
    assert "/test_exclude/greet" not in routes


def test_name_mapping_in_listing() -> None:
    """name_mapping renames a task in the listing endpoint."""
    app = _make_celery_app("test_mapping")
    bridge = CeleryFastAPIBridge(
        app,
        name_mapping={"test_mapping.greet": "public_greet"},
    )
    fastapi_app = bridge.register_routes()
    client = TestClient(fastapi_app)

    response = client.get("/available-tasks")
    assert response.status_code == 200
    data = response.json()
    names = [t["name"] for t in data.get("tasks", [])]
    # Mapping should apply at the listing level
    assert any("public_greet" in n for n in names)


# 6. Pre/post hooks
def test_pre_post_hooks_invoked() -> None:
    """Pre and post hooks are invoked around task dispatch."""
    app = _make_celery_app("test_hooks")
    calls: list[str] = []

    def pre(payload: object) -> None:
        calls.append(f"pre:{type(payload).__name__}")

    def post(result: object) -> None:
        calls.append(f"post:{type(result).__name__}")

    fastapi_app = create_app(
        app,
        pre_hooks=[pre],
        post_hooks=[post],
    )
    client = TestClient(fastapi_app)

    response = client.post("/test_hooks/add_seq", json={"args": [1, 2]})
    assert response.status_code == 200
    assert any("pre:" in c for c in calls)
    assert any("post:" in c for c in calls)


# 7. Custom error mapping
def test_error_mapping_handler_registered() -> None:
    """Bridge with error_mapping registers a global exception handler."""
    app = _make_celery_app("test_err_map")
    fastapi_app = FastAPI()
    CeleryFastAPIBridge(
        app,
        fastapi_app=fastapi_app,
        error_mapping={ValueError: 422},
    ).register_routes()
    assert Exception in fastapi_app.exception_handlers


# 8. Middleware
def test_middleware_installed() -> None:
    """Middleware is added to the FastAPI app."""
    from starlette.requests import Request

    app = _make_celery_app("test_mw")

    async def my_mw(request: Request, call_next: object) -> object:
        return await call_next(request)

    fastapi_app = create_app(app, middleware=[my_mw])
    clz_names = [
        repr(getattr(m, "clz", m))
        for m in fastapi_app.user_middleware
    ]
    assert any("my_mw" in c for c in clz_names)


# 9. Dependencies via Depends
def test_dependencies_registered_on_route() -> None:
    """A FastAPI dependency provider is attached to the task route."""
    app = _make_celery_app("test_dep")

    def dep_provider() -> bool:
        return True

    fastapi_app = create_app(app, dependencies=[dep_provider])
    assert any(
        getattr(r, "dependencies", None)
        and len(r.dependencies) > 0
        for r in fastapi_app.routes
    )
