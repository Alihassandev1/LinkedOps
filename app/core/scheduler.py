"""
Background Scheduler Setup
-----------------------------
Uses APScheduler's AsyncIOScheduler, running inside the same process as FastAPI.

This is intentionally simple for now — one process, in-memory job store.
Fine for a single-server deployment. If you scale to multiple backend instances
later, migrate this to Celery + Redis so jobs don't run duplicated on every instance.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.services.scheduler_jobs import publish_due_posts, refresh_expiring_tokens

logger = logging.getLogger("linkedops.scheduler")

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    """
    Register and start all background jobs.
    Called once on FastAPI startup (see app/main.py lifespan).
    """
    # Job 1: Check for due posts every minute
    scheduler.add_job(
        publish_due_posts,
        trigger=IntervalTrigger(minutes=1),
        id="publish_due_posts",
        name="Publish scheduled LinkedIn posts",
        replace_existing=True,
        max_instances=1,  # Don't let overlapping runs stack up if one is slow
        misfire_grace_time=30,  # If the scheduler was busy, still run within 30s
    )

    # Job 2: Refresh LinkedIn tokens daily at 3:00 AM UTC (low-traffic window)
    scheduler.add_job(
        refresh_expiring_tokens,
        trigger=CronTrigger(hour=3, minute=0),
        id="refresh_expiring_tokens",
        name="Refresh expiring LinkedIn tokens",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("APScheduler started: publish_due_posts (1 min), refresh_expiring_tokens (daily 3AM UTC)")


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler. Called on FastAPI shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")
