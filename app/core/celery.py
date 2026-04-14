"""Celery application configuration and task definitions.

Usage:
    Start worker: celery -A app.core.celery worker --loglevel=info
    Start beat:   celery -A app.core.celery beat --loglevel=info
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "multando",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Beat schedule for periodic tasks
    beat_schedule={
        "cleanup-expired-conversations": {
            "task": "app.tasks.cleanup_expired_conversations",
            "schedule": 300.0,  # Every 5 minutes
        },
        "sync-blockchain-balances": {
            "task": "app.tasks.sync_blockchain_balances",
            "schedule": 3600.0,  # Every hour
        },
        "calculate-staking-rewards": {
            "task": "app.tasks.calculate_staking_rewards",
            "schedule": 86400.0,  # Daily
        },
        "process-record-submissions": {
            "task": "app.integrations.record_task.process_pending_record_submissions",
            "schedule": 300.0,  # Every 5 minutes
        },
        "move-stale-pending": {
            "task": "app.tasks.move_stale_pending_reports",
            "schedule": 3600.0,  # Every hour
        },
    },
)
