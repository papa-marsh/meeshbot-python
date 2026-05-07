import json

import asyncpg
from anthropic import types

from meeshbot.config import AI_DATABASE_URL
from meeshbot.utils.logging import log

WEBSEARCH_TOOL: types.WebSearchTool20260209Param = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": 10,
}


WEBFETCH_TOOL: types.WebFetchTool20260209Param = {
    "type": "web_fetch_20260209",
    "name": "web_fetch",
    "max_uses": 5,
}

DB_QUERY_TOOL: types.ToolParam = {
    "name": "query_database",
    "description": (
        "Execute a read-only SQL SELECT query against the meeshbot Postgres database. "
        "Use this tool when you need to look up message history, user information, group details, "
        "or scheduled reminders that aren't already in the conversation context provided to you. "
        "Only SELECT statements are permitted — any attempt to INSERT, UPDATE, DELETE, DROP, "
        "or otherwise mutate data will be rejected. "
        "Results are returned as a JSON array of row objects. "
        "Limit each query to a reasonable number of rows (e.g. LIMIT 200) unless a larger result "
        "is necessary."
        "\n\n"
        "## Schema\n"
        "\n"
        "### groupmegroup\n"
        "Represents a GroupMe chat group (5-10 total).\n"
        "- id (text, PK): GroupMe's group ID\n"
        "- name (text): display name of the group\n"
        "- image_url (text, nullable): group avatar URL\n"
        "- created_at (timestamptz): when the group was first seen by meeshbot\n"
        "\n"
        "### groupmeuser\n"
        "Represents a GroupMe chat member (10-20 total).\n"
        "- id (text, PK): GroupMe's user ID\n"
        "- name (text): display name\n"
        "- image_url (text, nullable): avatar URL\n"
        "- muted (boolean): whether the bot ignores this user's messages\n"
        "\n"
        "### groupmemessage\n"
        "Every message sent in any tracked group (10k-100k total).\n"
        "- id (text, PK): GroupMe's message ID\n"
        "- group_id (text, FK → groupmegroup.id): which group the message was sent in\n"
        "- sender_id (text, FK → groupmeuser.id): who sent the message\n"
        "- text (text, nullable): message body (null for attachment-only messages)\n"
        "- system (boolean): true for system events (membership changes, etc.),"
        " false for user messages\n"
        "- attachments (jsonb): array of attachment objects from GroupMe (images, mentions, etc.)\n"
        "- timestamp (timestamptz): when the message was sent\n"
        "\n"
        "### reminder\n"
        "Scheduled reminders created via the /remindme slash command (10-100 total).\n"
        "- id (text, PK)\n"
        "- group_id (text, FK → groupmegroup.id): group where the reminder will be posted\n"
        "- sender_id (text, FK → groupmeuser.id): user who created the reminder\n"
        "- command_message_id (text): ID of the /remindme message that triggered this reminder\n"
        "- message (text): reminder text to be posted\n"
        "- eta (timestamptz): when the reminder is scheduled to fire\n"
        "- created_at (timestamptz): when the reminder was created\n"
        "- sent (boolean): whether the reminder has already been dispatched\n"
        "\n"
        "## Tips\n"
        "- Join groupmemessage with groupmeuser on sender_id = groupmeuser.id"
        " to get sender names.\n"
        "- Join groupmemessage with groupmegroup on group_id = groupmegroup.id"
        " to get group names.\n"
        "- Filter system = false to exclude membership-change events from message results.\n"
        "- Use timestamp ordering (ORDER BY timestamp DESC) for recent-message queries.\n"
        "- The current group's ID is available in the conversation context — use it to scope"
        " queries to the relevant group rather than returning data across all groups.\n"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": (
                    "A read-only SELECT query to execute. Must not contain any data-mutating "
                    "statements (INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, etc.)."
                ),
            }
        },
        "required": ["sql"],
    },
}

ERROR_PREFIX = "Error:"

_DISALLOWED_KEYWORDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "vacuum",
    "reindex",
}


def _is_safe_query(sql: str) -> bool:
    normalized = sql.lower()
    return not any(keyword in normalized for keyword in _DISALLOWED_KEYWORDS)


async def execute_db_query(sql: str) -> str:
    """
    Execute a read-only SELECT query against the database using the AI read-only user.

    Returns a JSON string of results on success, or an error string on failure.
    The caller is responsible for passing is_error=True to the tool_result when
    this function raises or returns an error-prefixed string.
    """
    if not _is_safe_query(sql):
        return f"{ERROR_PREFIX} query contains disallowed keywords. Only SELECTs are permitted."

    log.info("AI executing database query", sql=sql)

    conn: asyncpg.Connection = await asyncpg.connect(AI_DATABASE_URL)
    try:
        rows = await conn.fetch(sql)
        return json.dumps([dict(row) for row in rows], default=str)
    finally:
        await conn.close()
