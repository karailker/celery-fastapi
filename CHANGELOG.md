# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] - 2026-08-15

### Added

- Health check and ping endpoints now accept explicit `worker` query parameter
- Batch task execution endpoint (`/tasks/batch`) and revoke endpoint
- In-memory sliding-window rate limiter (`rate_limit` parameter on `create_app`)
- Input validation on `task_name` and `queue` with length limit (255 chars)
- WebSocket streaming for task status (`/tasks/{task_id}/ws`)
- Unit tests for new features (52 passing)
- Type-checking clean with `ValidationInfo` annotation

## [0.1.0] - 2024-XX-XX

### Added

- Initial release
- `CeleryFastAPIBridge` class for connecting Celery and FastAPI
- `create_app` factory function for quick setup
- CLI commands: `serve`, `routes`, `tasks`
- Automatic REST endpoint generation for Celery tasks
- Task status and listing endpoints
- Queue-aware task routing
- Full OpenAPI documentation support
- Support for Python 3.10, 3.11, and 3.12
