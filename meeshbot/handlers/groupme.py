from meeshbot.commands.registry import get_command_func
from meeshbot.integrations.anthropic.chat import send_ai_response, should_respond
from meeshbot.integrations.groupme.queries import sync_message_to_db
from meeshbot.integrations.groupme.types import GroupMeWebhookPayload


async def handle_groupme_webhook(webhook: GroupMeWebhookPayload) -> None:
    await sync_message_to_db(webhook)
    await _handle_slash_command(webhook)
    await _handle_ai_response(webhook)


async def _handle_slash_command(webhook: GroupMeWebhookPayload) -> None:
    if not webhook.text or webhook.text[0] != "/":
        return

    message_parts = webhook.text.split(" ")
    command = message_parts[0]
    func = get_command_func(command)

    await func(webhook)


async def _handle_ai_response(webhook: GroupMeWebhookPayload) -> None:
    if not webhook.text or webhook.name == "MeeshBot":
        return

    if await should_respond(webhook.group_id):
        await send_ai_response(webhook.group_id)
