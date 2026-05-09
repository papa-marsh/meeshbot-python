from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]

from meeshbot.config import TIMEZONE
from meeshbot.scheduled.message_sync import sync_recent_messages
from meeshbot.scheduled.reminders import send_due_reminders
from meeshbot.utils.dates import local_now
from meeshbot.utils.logging import log


async def scheduler_heartbeat() -> None:
    now = local_now()
    log.info("Scheduler heartbeat", hour=now.hour)


@asynccontextmanager
async def scheduler_lifespan() -> AsyncIterator[None]:
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    scheduler.add_job(
        scheduler_heartbeat,
        trigger="cron",
        hour="*",
        minute=0,
        id=scheduler_heartbeat.__name__,
    )
    scheduler.add_job(
        send_due_reminders,
        trigger="cron",
        hour="*",
        minute="*",
        id=send_due_reminders.__name__,
    )
    scheduler.add_job(
        sync_recent_messages,
        trigger="cron",
        hour=4,
        minute=0,
        id=sync_recent_messages.__name__,
    )

    scheduler.start()
    log.info("Scheduler started")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")
