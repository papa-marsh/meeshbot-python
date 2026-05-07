from datetime import datetime
from enum import StrEnum

from anthropic import AsyncAnthropic, types
from pydantic import BaseModel

from meeshbot.config import ANTHROPIC_API_KEY, TIMEZONE
from meeshbot.integrations.anthropic.tools import (
    DB_QUERY_TOOL,
    WEBFETCH_TOOL,
    WEBSEARCH_TOOL,
    execute_db_query,
)


class ClaudeModel(StrEnum):
    OPUS = "claude-opus-4-7"
    SONNET = "claude-sonnet-4-6"
    HAIKU = "claude-haiku-4-5"


DEFAULT_MODEL = ClaudeModel.SONNET
DEFAULT_MAX_TOKENS = 2048

ERROR_OUTPUT = "FAILED"


class _ResolvedTimestamp(BaseModel):
    iso: str


class _ResponseLikelihood(BaseModel):
    score: int


class AnthropicClient:
    def __init__(self, model: ClaudeModel = DEFAULT_MODEL) -> None:
        self._client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.model = model

    @classmethod
    def build_message_entry(
        cls,
        sender_name: str,
        timestamp: datetime,
        message: str,
    ) -> types.MessageParam:
        timestamp_string = timestamp.strftime("%b %-d %Y, %-I:%M%p")

        return types.MessageParam(
            role="assistant" if sender_name == "MeeshBot" else "user",
            content=f"{sender_name} ({timestamp_string}): {message}",
        )

    async def generate_response(
        self,
        messages: list[types.MessageParam],
        context: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        allow_webfetch: bool = True,
        allow_db_query: bool = True,
    ) -> str:
        conversation = list(messages)
        tools: list[types.ToolUnionParam] = []

        if allow_webfetch:
            tools.extend([WEBSEARCH_TOOL, WEBFETCH_TOOL])
        if allow_db_query:
            tools.append(DB_QUERY_TOOL)

        while True:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=context or "",
                messages=conversation,
                tools=tools,
            )

            if response.stop_reason != "tool_use":
                return "".join(block.text for block in response.content if block.type == "text")

            conversation.append({"role": "assistant", "content": response.content})
            tool_results: list[types.ToolResultBlockParam] = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                if block.name == DB_QUERY_TOOL["name"]:
                    raw_input = block.input
                    sql = str(raw_input.get("sql", "")) if isinstance(raw_input, dict) else ""
                    try:
                        result_content = await execute_db_query(sql)
                        is_error = result_content.startswith("Error:")
                    except Exception as exc:
                        result_content = f"Error: {exc}"
                        is_error = True

                    tool_results.append(
                        types.ToolResultBlockParam(
                            type="tool_result",
                            tool_use_id=block.id,
                            content=result_content,
                            is_error=is_error,
                        )
                    )

            if not tool_results:
                return "".join(block.text for block in response.content if block.type == "text")

            conversation.append({"role": "user", "content": tool_results})

    async def resolve_timestamp(self, description: str) -> str:
        """
        Resolve a natural-language date/time description to an ISO 8601 string.

        Handles both relative expressions ("next Wednesday at 7", "tomorrow afternoon")
        and absolute expressions ("March 23", "9/24/26").

        Returns an ISO 8601 datetime string (e.g. "2026-04-23T19:00:00").
        """
        now = datetime.now(tz=TIMEZONE)
        now_str = now.strftime("%A, %B %d, %Y %I:%M %p %Z")

        system = (
            f"You are a precise datetime parser. The current date and time is {now_str}. "
            "When given a natural-language date or time description, resolve it to a specific "
            "datetime and return it as an ISO 8601 string (YYYY-MM-DDTHH:MM:SS) with no "
            "timezone suffix. For vague times of day, use a reasonable default "
            "(morning=09:00, afternoon=14:00, evening=18:00, night=21:00). "
            "For dates with no time specified, use 10:00. "
            "Output ONLY the ISO 8601 string and nothing else. "
            "If for some reason, the input cannot be resolved "
            f"to a timestamp, output only the text: {ERROR_OUTPUT}"
        )

        response = await self._client.messages.parse(
            model=self.model,
            max_tokens=64,
            system=system,
            messages=[{"role": "user", "content": description}],
            output_format=_ResolvedTimestamp,
        )

        if response.parsed_output is None:
            raise ValueError(f"Failed to resolve timestamp from: {description!r}")

        return response.parsed_output.iso

    async def score_response_likelihood(self, history_text: str, context: str) -> int:
        """
        Score how likely it is that MeeshBot should respond, on a 0-100 scale.

        Chat history is passed as a single user-role text block (it is evidence
        to classify, not a conversation to participate in). The system prompt
        defines the scoring task and anchors.
        """
        response = await self._client.messages.parse(
            model=self.model,
            max_tokens=16,
            system=context,
            messages=[{"role": "user", "content": history_text}],
            output_format=_ResponseLikelihood,
        )

        if response.parsed_output is None:
            raise ValueError("Failed to score response likelihood")

        return response.parsed_output.score
