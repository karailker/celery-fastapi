# Celery FastAPI

[![CI](https://github.com/karailker/celery-fastapi/actions/workflows/ci.yml/badge.svg)](https://github.com/karailker/celery-fastapi/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/celery-fastapi.svg)](https://badge.fury.io/py/celery-fastapi)
[![Python Version](https://img.shields.io/pypi/pyversions/celery-fastapi.svg)](https://pypi.org/project/celery-fastapi/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Repo stars](https://img.shields.io/github/stars/karailker/celery-fastapi)](https://github.com/karailker/celery-fastapi/stargazers)

Automatic REST API generation for Celery tasks with FastAPI. This package seamlessly bridges Celery and FastAPI, automatically creating REST endpoints for all your registered Celery tasks.

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

## Requirements

- Python 3.11+
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

### Using the CLI

```bash
celery-fastapi serve examples.celery_app:celery_app --port 8000 --reload
celery-fastapi serve examples.celery_app:celery_app -w 4 --host 0.0.0.0
celery-fastapi routes examples.celery_app:celery_app
celery-fastapi tasks examples.celery_app:celery_app
celery-fastapi workers examples.celery_app:celery_app
```

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

`POST /trigger` — Trigger any task by name (`queue` required here).

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

`POST /tasks/batch/revoke` — Revoke tasks by list of IDs.

### Task Status

- `GET /tasks/{task_id}` — Full task status (state, result, traceback, date_done).
- `GET /tasks/{task_id}/result` — Task result only.
- `GET /tasks` — List active, scheduled, reserved, revoked tasks (filtered to this app).
- `DELETE /tasks/{task_id}` — Revoke a single task.

### Discovery & Management

- `GET /available-tasks` — List tasks registered in THIS app (respects `name_mapping`/`exclude`).
- `GET /workers` — List active workers, filtered to this app's tasks (includes `active_queues`).

### Health Check

- `GET /healthz` — Health check for local Celery worker.
- `GET /ping` — Ping local Celery worker.

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

Rate limiting is backed by `BaseRateLimitStorage` (abstract). Default is in-memory
(single-process). For multi-worker, implement the ABC against a shared store:

```python
from celery_fastapi import BaseRateLimitStorage


class RedisRateLimitStorage(BaseRateLimitStorage):
    def __init__(self, client): ...
    def prune(self, key, cutoff): ...
    def count(self, key): ...
    def add(self, key, now): ...


bridge = CeleryFastAPIBridge(
    celery_app,
    rate_limit=100,
    rate_limit_storage=RedisRateLimitStorage(redis_client),
)
```

`pip install celery-fastapi[redis]` provides the `redis` package for this.

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
celery-fastapi routes       List all generated routes
celery-fastapi tasks        List registered Celery tasks
celery-fastapi workers      Show active workers
```

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

## License

MIT License — see [LICENSE](LICENSE).
