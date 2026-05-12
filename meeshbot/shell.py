"""
Interactive shell with pre-loaded meeshbot context.
Run with: make shell
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

from oxyde import db

from meeshbot.config import DATABASE_URL, TESTING_GROUP_ID
from meeshbot.integrations.anthropic.chat import send_ai_response
from meeshbot.integrations.anthropic.client import AnthropicClient
from meeshbot.integrations.groupme.client import GroupMeClient
from meeshbot.models import GroupMeGroup, GroupMeMessage, GroupMeUser, Reminder
from meeshbot.utils.logging import log

asyncio.run(db.init(default=DATABASE_URL))

groupme = GroupMeClient()
anthropic = AnthropicClient()


async def mock_ai_response(group_id: str = TESTING_GROUP_ID) -> None:
    """Trigger the AI response pipeline without sending anything to GroupMe"""

    async def _log_message(group_id: str, text: str, **_kwargs: Any) -> None:
        log.info("Mock AI response", group_id=group_id, response=text)

    with patch.object(GroupMeClient, "post_message", new=AsyncMock(side_effect=_log_message)):
        await send_ai_response(group_id)
