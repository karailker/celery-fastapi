# Contributing

Thanks for helping! Bug reports, docs fixes and features are all welcome.

## Setup

```bash
git clone https://github.com/karailker/celery-fastapi.git
cd celery-fastapi
poetry install --extras all
```

## Checks (CI runs the same)

```bash
poetry run ruff check celery_fastapi tests
poetry run ruff format --check celery_fastapi tests
poetry run mypy celery_fastapi
poetry run pytest --ignore=tests/test_integration_broker_backend.py
```

CI pins Ruff 0.3.x; format with that version (`poetry run ruff format`) or the
lint job will fail on formatting differences.

The broker/backend matrix needs services and a worker:

```bash
docker compose up -d --wait
poetry run celery -A tests.broker_workers:live_app worker --loglevel=warning -P solo &
poetry run pytest tests/test_integration_broker_backend.py
```

## Pull requests

- Branch from `main` (or the current release branch) and keep PRs focused.
- Add or update tests; behaviour changes need a `CHANGELOG.md` entry.
- Use conventional commit prefixes (`feat:`, `fix:`, `docs:`, `test:`, `ci:`,
  `chore:`); a `!` marks a breaking change.
- Security-sensitive defaults (admin endpoints, auth, task exposure) should stay
  closed unless a caller opts in.

## Reporting security issues

Do not open a public issue; see [SECURITY.md](SECURITY.md).
