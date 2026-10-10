"""Quickstart Celery app. Broker and backend come from the environment."""

import os
import time

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("quickstart", broker=REDIS_URL, backend=REDIS_URL)


@celery_app.task(name="quickstart.add")
def add(x: int, y: int) -> int:
    return x + y


@celery_app.task(name="quickstart.slow_square")
def slow_square(n: int, delay: float = 2.0) -> int:
    time.sleep(delay)
    return n * n
