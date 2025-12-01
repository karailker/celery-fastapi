# Celery FastAPI

[![CI](https://github.com/karailker/celery-fastapi/actions/workflows/ci.yml/badge.svg)](https://github.com/karailker/celery-fastapi/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/celery-fastapi.svg)](https://badge.fury.io/py/celery-fastapi)
[![Python Version](https://img.shields.io/pypi/pyversions/celery-fastapi.svg)](https://pypi.org/project/celery-fastapi/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Automatic REST API generation for Celery tasks with FastAPI. This package seamlessly bridges Celery and FastAPI, automatically creating REST endpoints for all your registered Celery tasks.

## Features

- 🚀 **Automatic endpoint generation** - REST APIs created automatically for all Celery tasks
- 🔧 **Zero configuration** - Works out of the box with sensible defaults
- 📊 **Task monitoring** - Built-in endpoints for task status, revocation, and worker info
- 🎯 **App-scoped operations** - Only manages tasks from your specific Celery app, not the entire cluster
- 🖥️ **CLI support** - Run as a standalone server from command line
- 📦 **Modular design** - Use as a library or standalone application
- 🔄 **Queue-aware routing** - Respects Celery queue assignments
- 📝 **OpenAPI documentation** - Full Swagger/ReDoc support
- 🔒 **Production ready** - Full uvicorn/gunicorn support with SSL, workers, and all options
- ⚡ **Full Celery options** - All task options (countdown, eta, priority, etc.)
- 🔌 **Pool support** - Compatible with eventlet, gevent, prefork, and solo pools

## Requirements

- Python 3.11+
- FastAPI 0.100.0+
- Celery 5.3.0+

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

# With eventlet/gevent concurrency
pip install celery-fastapi[eventlet]
pip install celery-fastapi[gevent]

# All extras (recommended for production)
pip install celery-fastapi[all]
```

Or with Poetry:

```bash
poetry add celery-fastapi
poetry add celery-fastapi --extras cli  # for CLI support
```

## Quick Start

### As a Python Module

```python
from celery import Celery
from celery_fastapi import CeleryFastAPIBridge, create_app

# Your existing Celery app
celery_app = Celery('tasks', broker='redis://localhost:6379/0')

@celery_app.task
def add(x, y):
    return x + y

@celery_app.task
def multiply(x, y):
    return x * y

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
# Start the server (development)
celery-fastapi serve myapp.celery:celery_app --port 8000 --reload

# Production with multiple workers
celery-fastapi serve myapp.celery:celery_app -w 4 --host 0.0.0.0

# With SSL
celery-fastapi serve myapp.celery:celery_app --ssl-keyfile key.pem --ssl-certfile cert.pem

# Using gunicorn (production)
celery-fastapi serve-gunicorn myapp.celery:celery_app -w 4 -k uvicorn.workers.UvicornWorker

# List available routes
celery-fastapi routes myapp.celery:celery_app

# List registered tasks
celery-fastapi tasks myapp.celery:celery_app

# Show active workers
celery-fastapi workers myapp.celery:celery_app
```

## API Endpoints

Once running, your Celery tasks are available as REST endpoints:

### Task Execution

```bash
# Execute a task with basic args
POST /{task_name_with_slashes}
Content-Type: application/json

{
    "args": [1, 2],
    "kwargs": {}
}

# Execute with advanced Celery options
POST /myapp/process_data
Content-Type: application/json

{
    "args": ["data.csv"],
    "kwargs": {"output_format": "json"},
    "countdown": 60,
    "priority": 5,
    "queue": "high_priority",
    "time_limit": 300,
    "soft_time_limit": 280
}

# Response
{
    "task_id": "abc123-def456-...",
    "status": "PENDING"
}
```

### Task Status

```bash
# Get task status
GET /tasks/{task_id}

# Response
{
    "task_id": "abc123-def456-...",
    "state": "SUCCESS",
    "result": 3,
    "traceback": null,
    "date_done": "2024-01-15T10:30:00Z"
}
```

### Task Management

```bash
# Revoke a task
POST /tasks/{task_id}/revoke
Content-Type: application/json

{
    "terminate": true,
    "signal": "SIGTERM"
}

# Get task result only
GET /tasks/{task_id}/result

# List active workers (filtered to this app's tasks)
GET /workers

# List available tasks in THIS app
GET /available-tasks

# Response
{
    "app_name": "my_tasks",
    "task_count": 4,
    "tasks": [
        {"name": "my_tasks.add", "queue": "default", ...},
        {"name": "my_tasks.multiply", "queue": "default", ...}
    ]
}

# List queues
GET /queues

# Purge tasks from a queue
POST /purge
```

### List All Tasks

```bash
# List active, scheduled, reserved, and revoked tasks (filtered to this app only)
GET /tasks

# Response
{
    "active": {...},
    "scheduled": {...},
    "reserved": {...},
    "revoked": {...}
}
```

## Configuration

### CeleryFastAPIBridge Options

```python
bridge = CeleryFastAPIBridge(
    celery_app=celery_app,
    fastapi_app=fastapi_app,  # Optional, creates new if not provided
    prefix="/api/v1",         # URL prefix for all endpoints
    include_status_endpoints=True,  # Include /tasks endpoints
    task_filter=lambda name: not name.startswith("internal."),  # Filter tasks
)
```

### create_app Options

```python
app = create_app(
    celery_app,  # Celery instance or module path string
    title="My API",
    description="Task API",
    version="1.0.0",
    prefix="/api",
    include_status_endpoints=True,
    fastapi_kwargs={"docs_url": "/swagger"},
)
```

## Integration with Existing FastAPI App

```python
from fastapi import FastAPI
from celery_fastapi import CeleryFastAPIBridge
from myapp import celery_app

app = FastAPI()

# Your existing routes
@app.get("/health")
def health_check():
    return {"status": "healthy"}

# Add Celery task endpoints under /celery prefix
bridge = CeleryFastAPIBridge(
    celery_app,
    app,
    prefix="/celery",
)
bridge.register_routes()
```

## CLI Reference

```bash
celery-fastapi --help

Commands:
  serve            Start the FastAPI server with uvicorn
  serve-gunicorn   Start the FastAPI server with Gunicorn
  routes           List all generated routes
  tasks            List all registered Celery tasks
  workers          Show active Celery workers

# Serve options (uvicorn)
celery-fastapi serve myapp:celery_app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --workers 4 \
    --prefix /api \
    --log-level info \
    --ssl-keyfile key.pem \
    --ssl-certfile cert.pem \
    --proxy-headers \
    --forwarded-allow-ips '*'

# Serve options (gunicorn)
celery-fastapi serve-gunicorn myapp:celery_app \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --timeout 30 \
    --daemon \
    --pid /var/run/celery-fastapi.pid
```

## Development

```bash
# Clone the repository
git clone https://github.com/karailker/celery-fastapi.git
cd celery-fastapi

# Install dependencies
poetry install --extras all

# Run tests
poetry run pytest

# Run linting
poetry run ruff check .
poetry run mypy celery_fastapi

# Format code
poetry run ruff format .
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
