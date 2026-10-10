# Security Policy

## Supported versions

Security fixes are released for the latest minor version.

## Reporting a vulnerability

Please report privately through GitHub: **Security → Report a vulnerability** on
<https://github.com/karailker/celery-fastapi/security/advisories/new>.
Do not open a public issue for security problems.

Include the version, a minimal reproduction and the impact you expect. You can
expect an acknowledgement within a few days; fixes are released as a patch
version with a note in the changelog.

## Deployment guidance

celery-fastapi puts an HTTP API in front of your task queue:

- Keep `enable_admin_endpoints` off unless you need `/purge`, `/trigger` or
  revocation, and then protect them with `api_key` or `dependencies`.
- Terminate TLS in front of the service; API keys travel in a header.
- Pass secrets via environment variables, not command-line arguments.
- Use `exclude`/`task_filter` so only intended tasks are reachable.
- Use a shared `rate_limit_storage` (for example Redis) when running several
  processes; the in-memory limiter and idempotency store are per process.
