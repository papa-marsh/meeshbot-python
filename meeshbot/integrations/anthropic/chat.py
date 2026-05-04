from anthropic import types

from meeshbot.integrations.anthropic.client import AnthropicClient, ClaudeModel
from meeshbot.integrations.anthropic.context import (
    SEND_AI_RESPONSE_CONTEXT,
    SHOULD_RESPOND_CONTEXT,
)
from meeshbot.integrations.groupme.client import GroupMeClient
from meeshbot.integrations.groupme.queries import get_message_history
from meeshbot.integrations.groupme.types import GroupMeWebhookPayload
from meeshbot.models.user import GroupMeUser
from meeshbot.utils.logging import log

CHAT_HISTORY_MAX_DAYS = 14
CHAT_HISTORY_MAX_COUNT = 100

SHOULD_RESPOND_HISTORY_MAX_DAYS = 7
SHOULD_RESPOND_HISTORY_MAX_COUNT = 20
SHOULD_RESPOND_THRESHOLD = 50


async def build_message_history(
    group_id: str,
    max_days: int = CHAT_HISTORY_MAX_DAYS,
    max_count: int = CHAT_HISTORY_MAX_COUNT,
) -> list[types.MessageParam]:
    """
    Fetches message history for the specified group and
    returns it in the format required by Anthropic's API
    """
    context_messages: list[types.MessageParam] = []
    message_history_desc = await get_message_history(max_days, max_count, group_id=group_id)

    sender_name_map = {}

    for message in reversed(message_history_desc):
        user_id = message.sender_id or ""

        if user_id not in sender_name_map:
            user = await GroupMeUser.objects.get(id=user_id)
            sender_name_map[user_id] = user.name

        message_entry = AnthropicClient.build_message_entry(
            sender_name=sender_name_map[user_id],
            timestamp=message.timestamp,
            message=message.text or "",
        )
        context_messages.append(message_entry)

    return context_messages


async def should_respond(group_id: str, threshold: int = SHOULD_RESPOND_THRESHOLD) -> bool:
    """
    Decide whether MeeshBot should respond to the most recent message.

    Builds a recent-history block, asks the classifier model for a 0-100
    likelihood score, and returns True if the score meets the threshold.
    """
    message_history = await build_message_history(
        group_id=group_id,
        max_days=SHOULD_RESPOND_HISTORY_MAX_DAYS,
        max_count=SHOULD_RESPOND_HISTORY_MAX_COUNT,
    )

    prompt_lines = []
    for message in message_history[:-1]:
        if not isinstance(message["content"], str):
            raise TypeError

        prompt_lines.append(message["content"])

    prompt_lines.append("\n--- The message you are evaluating is: ---\n")
    most_recent_message = str(message_history[-1]["content"])
    prompt_lines.append(most_recent_message)

    client = AnthropicClient(model=ClaudeModel.HAIKU)
    score = await client.score_response_likelihood(
        history_text="\n".join(prompt_lines),
        context=SHOULD_RESPOND_CONTEXT,
    )

    log.info("LLM response confidence determined", confidence=score, message=most_recent_message)

    return score >= threshold


async def send_ai_response(webhook: GroupMeWebhookPayload) -> None:
    messages = await build_message_history(webhook.group_id)
    context = SEND_AI_RESPONSE_CONTEXT

    response = await AnthropicClient().generate_response(messages=messages, context=context)

    await GroupMeClient().post_message(
        group_id=webhook.group_id,
        text=response,
    )
