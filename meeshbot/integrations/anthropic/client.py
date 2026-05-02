from datetime import datetime
from enum import StrEnum

from anthropic import AsyncAnthropic, types
from pydantic import BaseModel

from meeshbot.config import ANTHROPIC_API_KEY, TIMEZONE


class ClaudeModel(StrEnum):
    OPUS = "claude-opus-4-7"
    SONNET = "claude-sonnet-4-6"
    HAIKU = "claude-haiku-4-5"


DEFAULT_MODEL = ClaudeModel.SONNET
DEFAULT_MAX_TOKENS = 2048

ERROR_OUTPUT = "FAILED"


class _ResolvedTimestamp(BaseModel):
    iso: str


class AnthropicClient:
    def __init__(self, model: ClaudeModel = DEFAULT_MODEL) -> None:
        self._client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.model = model

    @property
    def websearch_tool(self) -> types.WebSearchTool20260209Param:
        return {
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": 10,
        }

    @property
    def webfetch_tool(self) -> types.WebFetchTool20260209Param:
        return {
            "type": "web_fetch_20260209",
            "name": "web_fetch",
            "max_uses": 5,
        }

    async def generate_response(
        self,
        prompt: str,
        context: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        allow_webfetch: bool = False,
    ) -> str:
        """Generate a text response from Claude.

        Args:
            prompt: The user message.
            context: Optional system-level context (e.g. "You are a helpful assistant...").
            max_tokens: Maximum tokens in the response.

        Returns:
            The text content of Claude's response.
        """
        messages: list[types.MessageParam] = [{"role": "user", "content": prompt}]

        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=context or "",
            messages=messages,
            tools=[self.websearch_tool, self.webfetch_tool] if allow_webfetch else [],
        )

        return "".join(block.text for block in response.content if block.type == "text")

    async def resolve_timestamp(self, description: str) -> str:
        """Resolve a natural-language date/time description to an ISO 8601 string.

        Handles both relative expressions ("next Wednesday at 7", "tomorrow afternoon")
        and absolute expressions ("March 23", "9/24/26").

        Args:
            description: A natural-language date/time string.

        Returns:
            An ISO 8601 datetime string (e.g. "2026-04-23T19:00:00").
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
