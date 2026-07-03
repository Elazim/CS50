# apps/worker

The worker is the **same Python codebase as `apps/api`** with a different
entrypoint (docs/02 §1) — pipeline execution scales independently of the
API without forking the domain code.

Run locally:

```sh
make worker
# = cd apps/api && celery -A app.worker.celery_app:celery_app worker --loglevel=info
```

Deploy: build `apps/api/Dockerfile` and override the command with the
celery line above.
