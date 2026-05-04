"""Nightly message sync — backfills the last 7 days of messages across all groups."""

from datetime import UTC, datetime, timedelta

from meeshbot.integrations.groupme.client import GroupMeClient
from meeshbot.integrations.groupme.queries import upsert_message
from meeshbot.integrations.groupme.secrets import BOTS_BY_GROUP
from meeshbot.integrations.groupme.types import Message
from meeshbot.utils.dates import local_now
from meeshbot.utils.logging import log

SYNC_DAYS = 7
PAGE_SIZE = 100


async def sync_recent_messages() -> None:
    """Fetch and upsert the last 7 days of messages across all groups."""
    cutoff = local_now() - timedelta(days=SYNC_DAYS)
    client = GroupMeClient()
    total_synced = 0

    log.info(
        "Starting nightly message sync",
        group_count=len(BOTS_BY_GROUP),
        since=cutoff.isoformat(),
    )

    for group_id in BOTS_BY_GROUP:
        message_count = await sync_group_messages(client, group_id, cutoff)
        log.info("Group message sync complete", group_id=group_id, message_count=message_count)
        total_synced += message_count

    log.info("Nightly message sync complete", total_synced=total_synced)


async def sync_group_messages(client: GroupMeClient, group_id: str, cutoff: datetime) -> int:
    """
    Paginate backwards through a group's messages, upserting until past the cutoff.
    Returns the number of messages synced.
    """
    synced = 0
    before_id: str | None = None

    while True:
        page: list[Message] = await client.get_messages(
            group_id=group_id,
            before_id=before_id,
            limit=PAGE_SIZE,
        )

        if not page:
            break

        reached_cutoff = False
        for message in page:
            msg_time = datetime.fromtimestamp(message.created_at, tz=UTC)
            if msg_time < cutoff:
                reached_cutoff = True
                break

            await upsert_message(group_id=group_id, message=message)
            synced += 1

        if reached_cutoff or len(page) < PAGE_SIZE:
            break

        before_id = page[-1].id

    return synced
