# Quickstart

```bash
docker compose up --build
```

Open <http://localhost:8000/docs>, then:

```bash
# submit a task
curl -X POST localhost:8000/quickstart/add -H 'content-type: application/json' \
     -d '{"x": 2, "y": 3}'

# poll it (use the task_id from the response)
curl localhost:8000/tasks/<task_id>

# or stream it
curl -N localhost:8000/tasks/<task_id>/events
```

Without Docker: run Redis locally, then

```bash
celery -A tasks:celery_app worker --loglevel=info &
celery-fastapi serve tasks:celery_app --metrics
```
