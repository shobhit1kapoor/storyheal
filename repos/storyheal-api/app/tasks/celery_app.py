"""Celery configuration for analysis, webhook indexing, and evidence retention."""

from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "storyheal_knowledge",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.knowledge_ops"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={"app.tasks.knowledge_ops.*": {"queue": "knowledge"}},
    beat_schedule={
        "purge-expired-evidence-daily": {
            "task": "app.tasks.knowledge_ops.purge_expired_evidence_task",
            "schedule": 86400.0,
        },
        "recover-storyblok-webhooks": {
            "task": "app.tasks.knowledge_ops.recover_storyblok_webhooks",
            "schedule": 300.0,
        },
        "cluster-repeated-questions": {
            "task": "app.tasks.knowledge_ops.cluster_repeated_questions",
            "schedule": 3600.0,
        },
    },
)
