# Celery FastAPI

[![CI](https://github.com/karailker/celery-fastapi/actions/workflows/ci.yml/badge.svg)](https://github.com/karailker/celery-fastapi/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/celery-fastapi.svg)](https://badge.fury.io/py/celery-fastapi)
[![Python Version](https://img.shields.io/pypi/pyversions/celery-fastapi.svg)](https://pypi.org/project/celery-fastapi/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Repo stars](https://img.shields.io/github/stars/karailker/celery-fastapi)](https://github.com/karailker/celery-fastapi/stargazers)

Automatic REST API generation for Celery tasks with FastAPI. This package seamlessly bridges Celery and FastAPI, automatically creating REST endpoints for all your registered Celery tasks.

## Why celery-fastapi?

Without it, exposing Celery to other services means hand-writing a FastAPI
route, a request model and a status route for every task, then keeping them in
sync with the task signatures. celery-fastapi derives all of that from your
Celery app:

|  | Hand-written routes | celery-fastapi |
|---|---|---|
| New task becomes an endpoint | write route + model | automatic |
| Request validation / OpenAPI | per route | from the task signature and type hints |
| Status, revoke, workers, health | write yourself | built in |
| Auth, rate limit, idempotency, metrics | write yourself | one parameter each |
| Typed clients (TypeScript, Python, ...) | write the schema | `celery-fastapi openapi` |

It is a thin bridge, not a new task queue: workers, brokers and results stay
plain Celery.

## Features

- 🚀 **Automatic endpoint generation** — REST APIs created automatically for all Celery tasks
- 🔧 **Zero configuration** — Works out of the box with sensible defaults
- 📊 **Task monitoring** — Built-in endpoints for task status, revocation, and worker info
- 🎯 **App-scoped operations** — Only manages tasks from your specific Celery app, not the entire cluster
- 🖥️ **CLI support** — Run as a standalone server from command line
- 📦 **Modular design** — Use as a library or standalone application
- 🔄 **Queue-aware routing** — Respects Celery queue assignments
- 📝 **OpenAPI documentation** — Full Swagger/ReDoc support
- ⚡ **Full Celery options** — All task options (countdown, eta, priority, etc.)
- 🧮 **Batch execution** — Submit groups of tasks in a single request via `/tasks/batch`
- 🔗 **Workflow primitives** — Chain and chord orchestration via `/tasks/chain` and `/tasks/chord`
- 🛡️ **Input validation** — Pydantic-driven validation on `task_name`/`queue` at trust boundary
- 📦 **Pydantic task params** — Tasks annotated with `BaseModel` subclasses get first-class payload models and OpenAPI schemas
- 🪝 **Bridge hooks** — `pre_hooks`/`post_hooks` run around task dispatch (auth, audit, notify)
- 🗺️ **Discovery & mapping** — Hide tasks with `exclude` and rename public names with `name_mapping`
- 🔀 **Custom error mapping** — Map exception types to HTTP status codes via `error_mapping`
- 🧩 **Middleware & dependencies** — Inject FastAPI middleware and `Depends` providers
- 💾 **Pluggable rate limiting** — In-memory by default; bring your own store via `BaseRateLimitStorage`
- 🔌 **WebSocket streaming** — Live task status updates via `/tasks/{task_id}/ws`
- 📡 **Server-Sent Events** — Proxy-friendly status stream via `/tasks/{task_id}/events`
- 🔐 **Secure by default** — Destructive endpoints are opt-in; one `api_key` protects the rest
- ♻️ **Idempotency keys** — Retries with the same `Idempotency-Key` never double-submit
- 📈 **Prometheus metrics & OpenTelemetry** — Opt-in `/metrics` and dispatch spans
- 🗓️ **Beat schedule listing** — Read-only `/schedules`
- 🤖 **MCP server (experimental)** — Expose tasks as tools for AI agents
- 🧾 **OpenAPI export** — `celery-fastapi openapi` for client generation in CI

## Requirements

- Python 3.11 – 3.16 (3.11–3.14 tested in CI; 3.15 (release candidate) and 3.16 run as non-blocking jobs once available)
- FastAPI 0.100.0+
- Celery 5.3.0+ (tested up to 5.6.3)

## Installation

```bash
# Basic installation
pip install celery-fastapi

# With CLI support
pip install celery-fastapi[cli]

# With uvicorn server
pip install celery-fastapi[server]

# With gunicorn for production
pip install celery-fastapi[gunicorn]

# With Redis broker
pip install celery-fastapi[redis]

# With RabbitMQ broker
pip install celery-fastapi[rabbitmq]

# All extras (recommended for production)
pip install celery-fastapi[all]
```

Or with Poetry:

```bash
poetry add celery-fastapi
```

## Quick Start

### As a Python Module

```python
from celery import Celery
from celery_fastapi import CeleryFastAPIBridge, create_app

celery_app = Celery("tasks", broker="redis://localhost:6379/0")


@celery_app.task
def add(x, y):
    return x + y


# Option 1: Using create_app factory
app = create_app(celery_app)

# Option 2: Using the Bridge class for more control
from fastapi import FastAPI

fastapi_app = FastAPI(title="My Task API")
bridge = CeleryFastAPIBridge(celery_app, fastapi_app)
bridge.register_routes()
```

Run with uvicorn:

```bash
uvicorn myapp:app --reload
```

### Try it in five minutes

```bash
cd examples/quickstart && docker compose up --build   # then open http://localhost:8000/docs
```

See [examples/quickstart](examples/quickstart) and, for Kubernetes health probes,
[examples/k8s-sidecar.yaml](examples/k8s-sidecar.yaml).

### Using the CLI

```bash
celery-fastapi serve examples.celery_app:celery_app --port 8000 --reload
celery-fastapi serve examples.celery_app:celery_app -w 4 --host 0.0.0.0
celery-fastapi routes examples.celery_app:celery_app
celery-fastapi tasks examples.celery_app:celery_app
celery-fastapi workers examples.celery_app:celery_app
```

## Security

celery-fastapi is **secure by default**, because an HTTP API in front of a task
queue is a powerful thing to expose:

- **Admin endpoints are off.** `POST /purge`, `POST /trigger` (runs *any* task
  by name), `DELETE /tasks/{id}` and `POST /tasks/batch/revoke` only exist when
  you pass `enable_admin_endpoints=True` (`--enable-admin` on the CLI).
- **One key protects everything.** `api_key="..."` (`CELERY_FASTAPI_API_KEY`)
  requires the `X-API-Key` header (configurable) on every endpoint except the
  `/healthz` and `/ping` probes. WebSockets also accept `?api_key=`. Keys are
  compared in constant time.
- **Your own auth still works.** `dependencies=[...]` are applied to every HTTP
  endpoint except the probes (use them for OAuth/JWT).
- **Only your tasks.** Per-task, batch, chain and chord endpoints refuse task
  names outside the app; task and queue names are validated.
- **Rate limiting** covers every endpoint that submits work.

Always run it behind TLS, and prefer environment variables over command-line
arguments for secrets. See [SECURITY.md](SECURITY.md) for reporting issues.

> **Upgrading from 0.1.5:** if you call `/purge`, `/trigger` or the revoke
> endpoints, add `enable_admin_endpoints=True`. Everything else keeps working.

## API Endpoints

All endpoints are prefixed with the configured `prefix` (empty by default).

### Task Execution

`POST /{task_name_with_slashes}` — Execute a task.

```json
{
  "args": [1, 2],
  "kwargs": {},
  "countdown": 60,
  "priority": 5,
  "queue": "high_priority"
}
```

```json
{
  "task_id": "abc123-def456-...",
  "status": "PENDING"
}
```

Send an `Idempotency-Key` header to make retries safe: the same key with the
same body returns the original `task_id` (response header
`Idempotent-Replayed: true`); the same key with a different body returns `409`.
Keys are remembered in memory for `idempotency_ttl` seconds (24h by default),
per process.

`POST /trigger` *(admin)* — Trigger any task by name (`queue` required here).

```json
{
  "task_name": "myapp.add",
  "queue": "celery",
  "args": [1, 2]
}
```

#### Pydantic task parameters

When a task is annotated with a `pydantic.BaseModel` subclass, the generated
payload model uses that model directly, so nested schemas appear in OpenAPI:

```python
class Item(BaseModel):
    name: str
    qty: int = 1


@celery_app.task(name="myapp.process")
def process(payload: Item) -> dict:
    return payload.model_dump()
```

```json
{"payload": {"name": "widget", "qty": 3}}
```

### Workflow Primitives

`POST /tasks/chain` — Run tasks sequentially, passing results forward.

```json
{
  "tasks": [
    {"task_name": "myapp.add", "args": [1, 2]},
    {"task_name": "myapp.add", "args": [3, 4]}
  ]
}
```

`POST /tasks/chord` — Run a header group, then a callback once all complete.

```json
{
  "header": [
    {"task_name": "myapp.add", "args": [1, 2]},
    {"task_name": "myapp.add", "args": [3, 4]}
  ],
  "callback": "myapp.greet"
}
```

### Batch Execution

`POST /tasks/batch` — Submit a group of tasks.

`POST /tasks/batch/revoke` *(admin)* — Revoke tasks by list of IDs.

### Task Status

- `GET /tasks/{task_id}` — Full task status (state, result, traceback, date_done).
- `GET /tasks/{task_id}/result` — Task result only.
- `GET /tasks` — List active, scheduled, reserved, revoked tasks (filtered to this
  app). Query: `worker`, `name` (substring), `limit` and `offset` (per worker list).
- `GET /tasks/{task_id}/events` — Server-Sent Events status stream.
- `DELETE /tasks/{task_id}` *(admin)* — Revoke a single task.

A task that is unknown or has not started reports `state: "PENDING"` (HTTP 200),
which matches Celery; `GET /tasks/{id}/result` answers `202` until it finishes.

### Discovery & Management

- `GET /available-tasks` — List tasks registered in THIS app (respects `name_mapping`/`exclude`).
- `GET /workers` — List active workers, filtered to this app's tasks (includes `active_queues`).
- `GET /schedules` — Celery Beat entries (`beat_schedule`) for exposed tasks. Read-only:
  enabling/disabling entries depends on your scheduler and is not managed here.
- `POST /purge` *(admin)* — Purge all pending tasks.

### Health Check

- `GET /healthz` — Health check for local Celery worker.
- `GET /ping` — Ping local Celery worker.

### Observability

- `GET /metrics` *(opt-in: `enable_metrics=True`)* — Prometheus text format:
  `celery_fastapi_tasks_submitted_total{task}`, `..._dispatch_errors_total{task}`,
  `..._rate_limited_total`, `..._broker_up`, `..._workers_online`.
- **OpenTelemetry** *(opt-in: `enable_tracing=True`, `pip install celery-fastapi[otel]`)* —
  each dispatch runs in a `celery_fastapi.send_task` span with `celery.task_name`
  and `celery.queue` attributes, using whatever tracer provider your app configured.

### MCP (experimental)

`enable_mcp=True` adds `POST /mcp`, a minimal Model Context Protocol endpoint
(JSON-RPC over HTTP: `initialize`, `tools/list`, `tools/call`). Every exposed
task becomes a tool whose input schema comes from the task signature, plus a
`get_task_status` tool. It honours `api_key`, `dependencies`, hooks and the rate
limit. Streaming/SSE transports and resources/prompts are not implemented.

### Typed clients

```bash
celery-fastapi openapi myapp.celery:app -o openapi.json
npx @openapitools/openapi-generator-cli generate -i openapi.json -g typescript-fetch -o client
```

### WebSocket Streaming

`WS /tasks/{task_id}/ws` — Stream task status updates as JSON frames.

## Configuration

### CeleryFastAPIBridge Options

```python
from celery_fastapi import (
    CeleryFastAPIBridge,
    BaseRateLimitStorage,
)

bridge = CeleryFastAPIBridge(
    celery_app=celery_app,
    fastapi_app=fastapi_app,  # Optional
    prefix="/api/v1",  # URL prefix
    include_status_endpoints=True,
    task_filter=lambda name: not name.startswith("internal."),
    rate_limit=100,  # req/min per client
    rate_limit_storage=None,  # BaseRateLimitStorage instance
    enable_admin_endpoints=False,  # /purge, /trigger, revoke
    api_key=None,  # require X-API-Key everywhere except /healthz, /ping
    enable_metrics=False,  # /metrics (Prometheus)
    enable_mcp=False,  # /mcp (experimental)
    enable_tracing=False,  # OpenTelemetry spans
    idempotency_ttl=86400,  # seconds an Idempotency-Key is remembered
    exclude={"internal.secret"},  # Hide from API
    name_mapping={"my.add": "public_add"},  # Rename in listings
    middleware=[my_http_middleware],
    dependencies=[auth_provider],
    pre_hooks=[audit_hook],  # receive payload
    post_hooks=[notify_hook],  # receive response
    error_mapping={ValueError: 422},
)
```

### Pluggable Rate Limit Storage

Rate limiting is backed by `BaseRateLimitStorage`. The default is in-memory
(single process). For several workers use the bundled Redis store, or implement
the ABC for another shared store:

```python
from redis import Redis
from celery_fastapi import CeleryFastAPIBridge, RedisRateLimitStorage

bridge = CeleryFastAPIBridge(
    celery_app,
    rate_limit=100,
    rate_limit_storage=RedisRateLimitStorage(Redis()),
)
```

`pip install celery-fastapi[redis]` provides the `redis` package.

## Integration with Existing FastAPI App

```python
from fastapi import FastAPI
from celery_fastapi import CeleryFastAPIBridge

app = FastAPI()


@app.get("/health")
def health_check():
    return {"status": "healthy"}


bridge = CeleryFastAPIBridge(celery_app, app, prefix="/celery")
bridge.register_routes()
```

## CLI Reference

```
celery-fastapi serve        Start the server (uvicorn)
celery-fastapi serve-gunicorn  Start with Gunicorn
celery-fastapi openapi      Print the OpenAPI schema (no server)
celery-fastapi routes       List all generated routes
celery-fastapi tasks        List registered Celery tasks
celery-fastapi workers      Show active workers
```

`serve`, `serve-gunicorn`, `routes` and `openapi` accept `--enable-admin`,
`--api-key` (or `CELERY_FASTAPI_API_KEY`), `--metrics` and `--mcp`.

```bash
celery-fastapi serve examples.celery_app:celery_app \
    --host 0.0.0.0 --port 8000 --reload --workers 4 \
    --log-level info --ssl-keyfile key.pem --ssl-certfile cert.pem
```

## Development

```bash
git clone https://github.com/karailker/celery-fastapi.git
cd celery-fastapi
poetry install --extras all
poetry run pytest
poetry run ruff check .
poetry run mypy celery_fastapi
```

### Integration test suite (broker/backend matrix)

The repo ships a `docker-compose.yml` that brings up every broker/backend the
test matrix exercises:

```bash
docker compose up -d                              # redis, rabbitmq, postgres, mysql, memcached, mongodb
poetry run pytest tests/test_integration_broker_backend.py
```

Then start one worker for the end-to-end test and run it:

```bash
poetry run celery -A tests.broker_workers:live_app worker --loglevel=info
poetry run pytest tests/test_integration_broker_backend.py::test_live_redis_broker_backend
```

The matrix covers all stable Celery brokers (Redis, RabbitMQ) crossed with nine
result backends (redis, rpc, cache+memory, cache+memcached, db+sqlite,
db+postgresql, db+mysql, mongodb, filesystem) — 18 combinations, each verified
for bridge construction, broker dispatch, and result-backend round-trip. The
`rpc` backend skips the round-trip layer (it needs a live reply consumer); the
single live worker test uses Redis end to end. Missing drivers skip individually.

## Contributing & project

- [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, checks, PR conventions
- [SECURITY.md](SECURITY.md) — how to report a vulnerability
- [ROADMAP.md](ROADMAP.md) — what is shipped and what is next
- [CHANGELOG.md](CHANGELOG.md)

## License

MIT License — see [LICENSE](LICENSE).
