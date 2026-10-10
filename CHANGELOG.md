# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Rate limiting now also applies to `/trigger` and `/tasks/batch` (previously only per-task endpoints)
- Batch items are validated with the same task/queue name rules as `/trigger`
- Blocking Celery calls no longer run on the event loop (handlers are sync/threadpool, WebSocket polling uses `asyncio.to_thread`)
- Rate limiter is thread-safe
- Ruff/format issues under current Ruff (`StrEnum` for CLI enums)

### Added

- Tests for server utilities and rate limiting on all submit endpoints

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
