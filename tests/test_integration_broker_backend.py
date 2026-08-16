"""Integration tests for Celery broker/backend compatibility matrix.

Three layers:
  1. construct — every (broker, backend) combo builds a bridge with a live
     task route (no real worker needed).
  2. dispatch — POST to the bridge queues a real message on the broker and
     returns task_id + PENDING.
  3. backend_roundtrip — store_result/get_result through each backend store
     proves the result backend actually persists and reads back.

Requires `docker compose up -d` from repo root:
  redis, rabbitmq, postgres(5433), mysql, memcached, mongodb

Backends that need an extra driver skip automatically when it is missing:
  db+*  -> sqlalchemy (+ psycopg2 / pymysql)
  mongodb  -> pymongo
  cache+memcached -> python-memcached

The eager/cross-process caveat: cache+memory and rpc are worker-local and
cannot be shared across process boundaries, so the one end-to-end worker
test (test_live_redis_broker_backend) uses a Redis backend.
"""

from __future__ import annotations

import time

import pytest
from celery import Celery
from celery.result import AsyncResult
from fastapi.testclient import TestClient

from celery_fastapi import create_app

REDIS_URL = "redis://localhost:6379"
RABBIT_URL = "amqp://admin:admin@localhost:5672//"

# (name, broker, backend, driver-guard list)
# Filesystem path is module-level so the backend can write/read it.
FS_PATH = "/tmp/cf_fs_results"

MATRIX: list[tuple[str, str, str, list[str]]] = [
    ("redis+redis", f"{REDIS_URL}/11", f"{REDIS_URL}/12", []),
    ("redis+rpc", f"{REDIS_URL}/11", "rpc://", []),
    ("redis+cache_memory", f"{REDIS_URL}/11", "cache+memory://", []),
    (
        "redis+memcached",
        f"{REDIS_URL}/11",
        "cache+memcached://127.0.0.1:11211/",
        ["memcache"],
    ),
    (
        "redis+sqlite",
        f"{REDIS_URL}/11",
        "db+sqlite:////tmp/cf_matrix.db",
        ["sqlalchemy"],
    ),
    (
        "redis+postgresql",
        f"{REDIS_URL}/11",
        "db+postgresql+psycopg2://celery:celery@localhost:5433/celery",
        ["sqlalchemy", "psycopg2"],
    ),
    (
        "redis+mysql",
        f"{REDIS_URL}/11",
        "db+mysql+pymysql://celery:celery@localhost:3306/celery",
        ["sqlalchemy", "pymysql"],
    ),
    (
        "redis+mongodb",
        f"{REDIS_URL}/11",
        "mongodb://celery:celery@localhost:27017/celery_results",
        ["pymongo"],
    ),
    ("redis+filesystem", f"{REDIS_URL}/11", f"file://{FS_PATH}", []),
    ("rabbitmq+redis", RABBIT_URL, f"{REDIS_URL}/12", []),
    ("rabbitmq+rpc", RABBIT_URL, "rpc://", []),
    ("rabbitmq+cache_memory", RABBIT_URL, "cache+memory://", []),
    (
        "rabbitmq+memcached",
        RABBIT_URL,
        "cache+memcached://127.0.0.1:11211/",
        ["memcache"],
    ),
    ("rabbitmq+sqlite", RABBIT_URL, "db+sqlite:////tmp/cf_matrix.db", ["sqlalchemy"]),
    (
        "rabbitmq+postgresql",
        RABBIT_URL,
        "db+postgresql+psycopg2://celery:celery@localhost:5433/celery",
        ["sqlalchemy", "psycopg2"],
    ),
    (
        "rabbitmq+mysql",
        RABBIT_URL,
        "db+mysql+pymysql://celery:celery@localhost:3306/celery",
        ["sqlalchemy", "pymysql"],
    ),
    (
        "rabbitmq+mongodb",
        RABBIT_URL,
        "mongodb://celery:celery@localhost:27017/celery_results",
        ["pymongo"],
    ),
    ("rabbitmq+filesystem", RABBIT_URL, f"file://{FS_PATH}", []),
]

# Backends that cannot round-trip in a single process without a worker.
NO_ROUNDTRIP = {"rpc"}


def _make_app(name: str, broker: str, backend: str) -> Celery:
    app = Celery(name, broker=broker, backend=backend)
    app.conf.update(
        broker_connection_retry_on_startup=True,
        broker_connection_max_retries=3,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
    )

    @app.task(name=f"{name}.add")
    def add(x: int, y: int) -> int:
        return x + y

    return app


@pytest.mark.parametrize(
    "name,broker,backend,guards",
    MATRIX,
    ids=[m[0] for m in MATRIX],
)
def test_bridge_builds_for_combo(
    name: str, broker: str, backend: str, guards: list[str]
) -> None:
    """Every (broker, backend) combo builds a bridge exposing the task route."""
    for mod in guards:
        pytest.importorskip(mod)
    app = _make_app(name, broker, backend)
    fa = create_app(app)
    assert any(r.path == f"/{name}/add" for r in fa.routes)


@pytest.mark.parametrize(
    "name,broker,backend,guards",
    MATRIX,
    ids=[m[0] for m in MATRIX],
)
def test_dispatch_queues_to_broker(
    name: str, broker: str, backend: str, guards: list[str]
) -> None:
    """POST to the bridge queues a real message and returns task_id + PENDING."""
    for mod in guards:
        pytest.importorskip(mod)
    app = _make_app(name, broker, backend)
    fa = create_app(app)
    client = TestClient(fa)
    resp = client.post(f"/{name}/add", json={"x": 1, "y": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PENDING"
    assert "task_id" in body


@pytest.mark.parametrize(
    "name,broker,backend,guards",
    MATRIX,
    ids=[m[0] for m in MATRIX],
)
def test_backend_roundtrip(
    name: str, broker: str, backend: str, guards: list[str]
) -> None:
    """store_result then get_result through the backend store, no worker."""
    for mod in guards:
        pytest.importorskip(mod)
    if backend.split(":", 1)[0] in NO_ROUNDTRIP:
        pytest.skip("rpc backend needs a live reply consumer")
    app = _make_app(name, broker, backend)
    task_id = f"rt-{name}"
    app.backend.store_result(task_id, 42, state="SUCCESS")
    assert app.AsyncResult(task_id).get(timeout=10) == 42


def test_live_redis_broker_backend() -> None:
    """End-to-end: real worker + Redis broker + Redis backend.

    Run the worker first:
        celery -A tests.broker_workers:live_app worker --loglevel=info
    """
    from tests.broker_workers import live_app

    fa = create_app(live_app)
    client = TestClient(fa)

    resp = client.post("/live_redis/add", json={"x": 40, "y": 2})
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    result = AsyncResult(task_id, app=live_app)
    deadline = time.time() + 30
    while not result.ready() and time.time() < deadline:
        time.sleep(0.5)
    assert result.ready(), "task did not finish within 30s"
    assert result.result == 42
