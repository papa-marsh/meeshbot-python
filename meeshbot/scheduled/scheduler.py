"""APScheduler configuration and lifespan context manager."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

from meeshbot.config import TIMEZONE
from meeshbot.scheduled.message_sync import sync_recent_messages
from meeshbot.scheduled.reminders import send_due_reminders
from meeshbot.utils.logging import log


async def _tick() -> None:
    """Run on every scheduled tick (once per minute)."""
    now = datetime.now(tz=UTC)
    if now.minute == 0:
        log.info("Scheduler heartbeat", hour=now.hour)

    await send_due_reminders()


@asynccontextmanager
async def scheduler_lifespan() -> AsyncIterator[None]:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        _tick,
        trigger="cron",
        minute="*",
        id="minute_tick",
    )
    scheduler.add_job(
        sync_recent_messages,
        trigger="cron",
        hour=4,
        minute=0,
        id="nightly_message_sync",
    )

    scheduler.start()
    log.info("Scheduler started")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
