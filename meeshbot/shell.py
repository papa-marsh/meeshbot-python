"""
Interactive shell with pre-loaded meeshbot context.
Run with: make shell
"""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

from anthropic.types import MessageParam
from oxyde import db

from meeshbot.config import DATABASE_URL, TESTING_GROUP_ID, TIMEZONE
from meeshbot.integrations.anthropic import chat as anthropic_chat
from meeshbot.integrations.anthropic.chat import build_message_history, send_ai_response
from meeshbot.integrations.anthropic.client import AnthropicClient
from meeshbot.integrations.groupme.client import GroupMeClient
from meeshbot.models import GroupMeGroup, GroupMeMessage, GroupMeUser, Reminder
from meeshbot.utils.logging import log

asyncio.run(db.init(default=DATABASE_URL))

groupme = GroupMeClient()
anthropic = AnthropicClient()


async def mock_ai_response(
    message: str,
    group_id: str = TESTING_GROUP_ID,
) -> None:
    """Trigger the AI response pipeline without sending anything to GroupMe"""

    async def _build_message_history_with_injection(gid: str, **kwargs: Any) -> list[MessageParam]:
        history = await build_message_history(gid, **kwargs)
        history.append(
            AnthropicClient.build_message_history_entry(
                sender_name="Marshall",
                timestamp=datetime.now(tz=TIMEZONE),
                message=message,
            )
        )
        return history

    async def _log_message(group_id: str, text: str, **_kwargs: Any) -> None:
        log.info("Mock AI response", group_id=group_id, response=text)

    with (
        patch.object(
            anthropic_chat,
            "build_message_history",
            side_effect=_build_message_history_with_injection,
        ),
        patch.object(GroupMeClient, "post_message", new=AsyncMock(side_effect=_log_message)),
    ):
        await send_ai_response(group_id)
