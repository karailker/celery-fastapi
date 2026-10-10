# Roadmap

## Shipped in 0.1.6

- Secure by default: opt-in admin endpoints, `api_key`, dependencies on all routes
- Idempotency keys, Prometheus metrics, OpenTelemetry spans
- Server-Sent Events, read-only Beat listing, task list filters and paging
- Experimental MCP endpoint, `celery-fastapi openapi` for client generation
- Pluggable (Redis) rate limiting, chain/chord, hooks, error mapping, middleware
- Python 3.11 - 3.14 tested; 3.15 and 3.16 join CI as they are released

## Next

- Shared (Redis) idempotency store so keys work across processes
- Per-task permissions / scopes (which client may call which task)
- Managing Beat entries for database-backed schedulers
- MCP streamable HTTP/SSE transport, resources and prompts
- Documentation site and a gallery of deployment recipes

Ideas and votes are welcome in GitHub issues.
