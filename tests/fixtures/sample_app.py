"""Importable Celery app used by CLI and loader tests."""

from celery import Celery

celery_app = Celery("sample", broker="memory://", backend="cache+memory://")


@celery_app.task(name="sample.add")
def add(x: int, y: int) -> int:
    return x + y


not_celery = object()
