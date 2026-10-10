"""Tests for the 0.1.6 additions: metrics, SSE, idempotency, schedules, MCP, tracing."""

import json
from typing import Any

import pytest
from celery import Celery
from fastapi.testclient import TestClient

from celery_fastapi import create_app

INSPECT = "celery.app.control.Inspect"


@pytest.fixture
def celery_app() -> Celery:
    app = Celery("feat", broker="memory://", backend="cache+memory://")
    app.conf.task_always_eager = False

    @app.task(name="feat.add")
    def add(x: int, y: int) -> int:
        return x + y

    @app.task(name="feat.hidden")
    def hidden() -> str:
        return "x"

    app.conf.beat_schedule = {
        "add-every-minute": {"task": "feat.add", "schedule": 60.0, "args": (1, 2)},
        "not-exposed": {"task": "celery.backend_cleanup", "schedule": 10.0},
    }
    return app


def _ids(client: TestClient, key: str | None = None, **body: Any) -> Any:
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/feat/add", json={"x": 1, "y": 2, **body}, headers=headers)


# ---------------------------------------------------------------- idempotency
def test_idempotency_key_replays_same_task(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app))
    first = _ids(client, "k1")
    second = _ids(client, "k1")
    assert first.json()["task_id"] == second.json()["task_id"]
    assert second.headers["Idempotent-Replayed"] == "true"
    assert "Idempotent-Replayed" not in first.headers


def test_without_key_each_call_is_a_new_task(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app))
    assert _ids(client).json()["task_id"] != _ids(client).json()["task_id"]


def test_idempotency_key_reuse_with_other_payload_conflicts(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app))
    assert _ids(client, "k2").status_code == 200
    assert (
        client.post(
            "/feat/add", json={"x": 9, "y": 9}, headers={"Idempotency-Key": "k2"}
        ).status_code
        == 409
    )


def test_idempotency_applies_to_trigger(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app, enable_admin_endpoints=True))
    body = {"task_name": "feat.add", "queue": "celery", "args": [1, 2]}
    h = {"Idempotency-Key": "t1"}
    a = client.post("/trigger", json=body, headers=h).json()["task_id"]
    b = client.post("/trigger", json=body, headers=h).json()["task_id"]
    assert a == b


# -------------------------------------------------------------------- metrics
def test_metrics_disabled_by_default(celery_app: Celery) -> None:
    assert TestClient(create_app(celery_app)).get("/metrics").status_code == 404


def test_metrics_counts_submissions(
    celery_app: Celery, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(f"{INSPECT}.ping", lambda *_a, **_k: {"w@h": {"ok": "pong"}})
    client = TestClient(create_app(celery_app, enable_metrics=True))
    _ids(client)
    _ids(client)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert 'celery_fastapi_tasks_submitted_total{task="feat.add"} 2' in resp.text
    assert "celery_fastapi_workers_online 1.0" in resp.text
    assert "celery_fastapi_broker_up 1.0" in resp.text


def test_metrics_counts_rate_limited_requests(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app, enable_metrics=True, rate_limit=1))
    _ids(client)
    assert _ids(client).status_code == 429
    assert "celery_fastapi_rate_limited_total 1" in client.get("/metrics").text


def test_metrics_respects_api_key(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app, enable_metrics=True, api_key="k"))
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-API-Key": "k"}).status_code == 200


# ------------------------------------------------------------------------ SSE
def test_sse_streams_until_ready() -> None:
    app = Celery("sse", broker="memory://", backend="cache+memory://")
    app.conf.update(task_always_eager=True, task_store_eager_result=True)

    @app.task(name="sse.add")
    def add(x: int, y: int) -> int:
        return x + y

    task_id = add.delay(2, 3).id
    client = TestClient(create_app(app))
    with client.stream("GET", f"/tasks/{task_id}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    assert "event: status" in body
    frame = json.loads(body.split("data: ", 1)[1].split("\n", 1)[0])
    assert frame["state"] == "SUCCESS"
    assert frame["result"] == 5


# ------------------------------------------------------------------ schedules
def test_schedules_lists_only_exposed_tasks(celery_app: Celery) -> None:
    data = (
        TestClient(create_app(celery_app, name_mapping={"feat.add": "add"}))
        .get("/schedules")
        .json()
    )
    assert data["count"] == 1
    entry = data["schedules"][0]
    assert entry["name"] == "add-every-minute"
    assert entry["task"] == "add"
    assert entry["args"] == [1, 2]


# ----------------------------------------------------------------- pagination
def test_task_list_filters_and_pagination(
    celery_app: Celery, monkeypatch: pytest.MonkeyPatch
) -> None:
    tasks = {
        "w1@h": [{"name": "feat.add", "id": str(i)} for i in range(5)]
        + [{"name": "other.task", "id": "x"}],
        "w2@h": [{"name": "feat.add", "id": "y"}],
    }
    monkeypatch.setattr(f"{INSPECT}.active", lambda *_a, **_k: tasks)
    monkeypatch.setattr(f"{INSPECT}.scheduled", lambda *_a, **_k: {})
    monkeypatch.setattr(f"{INSPECT}.reserved", lambda *_a, **_k: {})
    monkeypatch.setattr(f"{INSPECT}.revoked", lambda *_a, **_k: {"w1@h": ["r"]})
    client = TestClient(create_app(celery_app))

    full = client.get("/tasks").json()["active"]
    assert len(full["w1@h"]) == 5  # other.task is not this app's
    page = client.get("/tasks", params={"limit": 2, "offset": 1}).json()["active"]
    assert [t["id"] for t in page["w1@h"]] == ["1", "2"]
    only = client.get("/tasks", params={"worker": "w2@h"}).json()
    assert list(only["active"]) == ["w2@h"]
    assert only["revoked"] == {}
    assert client.get("/tasks", params={"limit": 0}).status_code == 422
    assert client.get("/tasks", params={"name": "nomatch"}).json()["active"] == {}


# ------------------------------------------------------------------------ MCP
def _rpc(client: TestClient, method: str, params: Any = None, rpc_id: int | None = 1):
    body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if rpc_id is not None:
        body["id"] = rpc_id
    if params is not None:
        body["params"] = params
    return client.post("/mcp", json=body)


def test_mcp_disabled_by_default(celery_app: Celery) -> None:
    assert _rpc(TestClient(create_app(celery_app)), "ping").status_code == 404


def test_mcp_initialize_and_list_tools(celery_app: Celery) -> None:
    client = TestClient(
        create_app(celery_app, enable_mcp=True, exclude={"feat.hidden"})
    )
    init = _rpc(client, "initialize", {"protocolVersion": "2025-03-26"}).json()
    assert init["result"]["serverInfo"]["name"] == "celery-fastapi"
    assert _rpc(client, "notifications/initialized", rpc_id=None).status_code == 202

    tools = {t["name"]: t for t in _rpc(client, "tools/list").json()["result"]["tools"]}
    assert "feat.add" in tools
    assert "feat.hidden" not in tools
    assert "get_task_status" in tools
    schema = tools["feat.add"]["inputSchema"]
    assert set(schema["properties"]) == {"x", "y"}
    assert set(schema["required"]) == {"x", "y"}


def test_mcp_call_dispatches_task_and_reports_status(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app, enable_mcp=True, enable_metrics=True))
    call = _rpc(
        client, "tools/call", {"name": "feat.add", "arguments": {"x": 1, "y": 2}}
    )
    result = call.json()["result"]
    assert result["isError"] is False
    task_id = json.loads(result["content"][0]["text"])["task_id"]
    status = _rpc(
        client,
        "tools/call",
        {"name": "get_task_status", "arguments": {"task_id": task_id}},
    ).json()["result"]
    assert json.loads(status["content"][0]["text"])["task_id"] == task_id


def test_mcp_invalid_arguments_and_unknown_tool(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app, enable_mcp=True))
    bad = _rpc(client, "tools/call", {"name": "feat.add", "arguments": {"x": "nope"}})
    assert bad.json()["result"]["isError"] is True
    unknown = _rpc(client, "tools/call", {"name": "missing", "arguments": {}}).json()
    assert unknown["error"]["code"] == -32602
    assert _rpc(client, "nope").json()["error"]["code"] == -32601


def test_mcp_requires_api_key(celery_app: Celery) -> None:
    client = TestClient(create_app(celery_app, enable_mcp=True, api_key="k"))
    assert _rpc(client, "ping").status_code == 401


# -------------------------------------------------------------------- tracing
def test_tracing_creates_span(celery_app: Celery) -> None:
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    client = TestClient(create_app(celery_app, enable_tracing=True))
    _ids(client)
    spans = [
        s for s in exporter.get_finished_spans() if s.name == "celery_fastapi.send_task"
    ]
    assert spans
    assert spans[0].attributes["celery.task_name"] == "feat.add"


def test_tracing_without_opentelemetry_raises(
    celery_app: Celery, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setitem(sys.modules, "opentelemetry", None)
    with pytest.raises(ImportError, match="celery-fastapi\\[otel\\]"):
        create_app(celery_app, enable_tracing=True)
