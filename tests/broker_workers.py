"""Worker apps for broker/backend integration tests.

Run one worker per broker:
    celery -A tests.broker_workers:redis_app worker --loglevel=info
    celery -A tests.broker_workers:rabbit_app worker --loglevel=info
    celery -A tests.broker_workers:redis_both_app worker --loglevel=info
    celery -A tests.broker_workers:redis_rpc_app worker --loglevel=info
    celery -A tests.broker_workers:live_app worker --loglevel=info  # live test
"""

from celery import Celery

REDIS_URL = "redis://localhost:6379"

redis_app = Celery(
    "test_redis",
    broker=f"{REDIS_URL}/1",
    backend="cache+memory://",
)

rabbit_app = Celery(
    "test_rabbitmq",
    broker="amqp://admin:admin@localhost:5672//",
    backend="cache+memory://",
)

redis_both_app = Celery(
    "test_redis_both",
    broker=f"{REDIS_URL}/2",
    backend=f"{REDIS_URL}/3",
)

redis_rpc_app = Celery(
    "test_redis_rpc",
    broker=f"{REDIS_URL}/4",
    backend="rpc://",
)

# Dedicated app for live end-to-end test (broker + backend both Redis).
live_app = Celery(
    "live_redis",
    broker=f"{REDIS_URL}/5",
    backend=f"{REDIS_URL}/5",
)
live_app.conf.update(broker_connection_retry_on_startup=True)


@redis_app.task
def add(x: int, y: int) -> int:
    return x + y


@rabbit_app.task
def buffered_tasks(x: int) -> int:
    return x * 100


@redis_both_app.task
def fib(n: int) -> int:
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


@redis_rpc_app.task
def complex_calc(x: int) -> int:
    return (x * 7) % 13


@live_app.task(name="live_redis.add")
def live_add(x: int, y: int) -> int:
    return x + y
