# PLAN.md

1. [x] Merge `feature/healthz-ping` into `main` → verify: `tests/test_core.py` passes.
2. [x] Final code review pass → lint/format/mypy clean, rate limit + validation gaps fixed.
3. [ ] Raise test coverage (cli.py ~23%, core.py ~56%) → verify: coverage >= 80%.
4. [ ] Reconsider `GET /tasks/{id}` returning 404 for PENDING (indistinguishable from just-submitted tasks).
5. [ ] Cut release 0.1.4 → verify: CI + publish workflow green.
