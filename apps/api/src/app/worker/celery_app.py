from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "atc",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.worker.tasks"],
)
celery_app.conf.update(
    task_always_eager=settings.celery_task_always_eager,
    task_acks_late=True,  # a killed worker requeues the task; checkpoints make the retry cheap
    worker_prefetch_multiplier=1,  # pipelines are long; don't hoard queued runs
    task_serializer="json",
    accept_content=["json"],
)
