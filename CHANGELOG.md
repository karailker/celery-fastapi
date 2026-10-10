# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.6] - 2026-08-16

### Changed

- `GET /tasks/{id}` now returns `200` with `state: PENDING` for unknown or not-yet-started tasks (previously `404`, which made freshly submitted tasks look missing). `GET /tasks/{id}/result` returns `202` in that case.

### Added

- Python 3.14, 3.15 and 3.16 support. 3.14 is tested in CI; 3.15 (release candidate) and 3.16 run as non-blocking CI jobs, and 3.16 joins the matrix automatically once `setup-python` can install it.
- Tests for CLI commands, app loading, gunicorn integration, health/ping discovery and rate limiting (coverage 52% -> 77%).
- Pydantic task parameter support: `_create_task_payload_model` now directly uses BaseModel subclasses for type-hinted task parameters.
- Pluggable rate limiting: Introduced `BaseRateLimitStorage` with `InMemoryRateLimitStorage` and optional `RedisRateLimitStorage`.
- Chain and Chord workflow primitives: Added `/tasks/chain` and `/tasks/chord` endpoints.
- Bridge hooks: Added `pre_hooks` and `post_hooks` support in `CeleryFastAPIBridge`.
- Task discovery & mapping: Added `exclude` and `name_mapping` configuration.
- Custom error mapping: Added `error_mapping` in bridge to translate exceptions into custom HTTP status codes.
- Bridge Middleware & Dependencies: `CeleryFastAPIBridge` and `create_app` now accept `middleware` and `dependencies`.
- `docker-compose.yml` dev & test suite: Redis, RabbitMQ, PostgreSQL, MySQL, Memcached, MongoDB.
- Integration test matrix covering 18 broker/backend combinations (Redis/RabbitMQ × 9 backends) with construct, dispatch, and backend round-trip layers plus a live end-to-end worker test.

### Fixed

- Rate limiting now also applies to `/trigger`, `/tasks/batch`, `/tasks/chain` and `/tasks/chord`; the limiter is thread-safe.
- Batch/chain items are validated with the same task and queue name rules as `/trigger`.
- Blocking Celery calls no longer run on the event loop (sync handlers run in the threadpool; WebSocket polling uses `asyncio.to_thread`).
- mypy errors for `*args` / `**kwargs` payload fields and the `dependencies` annotation.
- `*args` (VAR_POSITIONAL) task params were sent as kwargs to `send_task`, causing `TypeError` at runtime; now routed to `args`.
- Chain and chord endpoints accepted arbitrary task names outside the app scope; now validated against registered tasks (404 on unknown).
- `RedisRateLimitStorage` ZSET member collision on identical timestamps undercounted rate-limit hits; a per-instance sequence counter disambiguates members.

## [0.1.5] - 2026-08-15

### Added

- Automated release workflow with dynamic versioning and PyPI trusted publishing.
- Improved CI/CD pipeline using git-cliff binary instead of Docker images.
- Refactored workflow triggers to support tag-based publishing.
- Added release management automation and cleanup scripts.

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
