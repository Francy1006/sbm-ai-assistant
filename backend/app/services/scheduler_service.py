from app.config.settings import CONFLUENCE_SYNC_INTERVAL_MINUTES
import logging
from apscheduler.schedulers.background import BackgroundScheduler

from app.services.confluence.confluence_sync_service import sync_confluence_pages

logger = logging.getLogger("scheduler")

scheduler = BackgroundScheduler()


def run_confluence_sync(ingest_page_func):
    logger.warning("[SCHEDULER] Running Confluence sync...")

    result = sync_confluence_pages(ingest_page_func)

    logger.warning("[SCHEDULER] Sync result: %s", result)


def start_scheduler(ingest_page_func):
    interval_minutes = int(CONFLUENCE_SYNC_INTERVAL_MINUTES)

    logger.warning(
        "[SCHEDULER] Starting scheduler every %s minutes...",
        interval_minutes
    )

    scheduler.add_job(
        run_confluence_sync,
        trigger="interval",
        minutes=interval_minutes,
        id="confluence_sync_job",
        replace_existing=True,
        args=[ingest_page_func],
    )

    scheduler.start()

    logger.warning("[SCHEDULER] Scheduler started.")