from http import HTTPMethod
from typing import Any

import httpx

from meeshbot.config import GROUPME_TOKEN
from meeshbot.integrations.groupme.queries import get_bot_id
from meeshbot.integrations.groupme.types import Group, Message, MessageAttachment
from meeshbot.utils.logging import log

BASE_URL = "https://api.groupme.com/v3"


class GroupMeClient:
    def __init__(self, api_token: str | None = None) -> None:
        self.api_token = api_token or GROUPME_TOKEN

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> list | dict:
        url = f"{BASE_URL}{path}"
        request_params = {"token": self.api_token, **(params or {})}

        log.debug("Sending request to GroupMe", method=HTTPMethod.GET, url=url)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=request_params,
                timeout=10,
            )
        log.debug("Received GroupMe response", status=response.status_code, url=str(response.url))

        response.raise_for_status()
        data = response.json()["response"]

        if not isinstance(data, list | dict):
            raise TypeError

        return data

    async def _post(self, path: str, json: dict[str, Any] | None = None) -> dict | None:
        url = f"{BASE_URL}{path}"
        request_params = {"token": self.api_token}

        log.debug("Sending request to GroupMe", method=HTTPMethod.POST, url=url)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                params=request_params,
                json=json,
                timeout=10,
            )
        log.debug("Received GroupMe response", status=response.status_code, url=str(response.url))

        response.raise_for_status()
        if not response.content:
            return None

        data = response.json().get("response")

        if not isinstance(data, dict | None):
            raise TypeError

        return data

    async def post_message(
        self,
        group_id: str,
        text: str,
        attachments: list[MessageAttachment] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "bot_id": get_bot_id(group_id, raise_if_missing=True),
            "text": text,
        }
        if attachments:
            payload["attachments"] = [a.model_dump() for a in attachments]

        await self._post("/bots/post", json=payload)

    async def get_groups(self, page: int = 1, per_page: int = 100) -> list[Group]:
        params = {
            "page": page,
            "per_page": per_page,
        }
        data = await self._get("/groups", params)

        return [Group.model_validate(g) for g in data]

    async def get_group(self, group_id: str) -> Group:
        data = await self._get(f"/groups/{group_id}")

        return Group.model_validate(data)

    async def get_messages(
        self,
        group_id: str,
        before_id: str | None = None,
        since_id: str | None = None,
        after_id: str | None = None,
        limit: int = 100,
    ) -> list[Message]:
        params: dict[str, Any] = {"limit": limit}

        if before_id is not None:
            params["before_id"] = before_id
        if since_id is not None:
            params["since_id"] = since_id
        if after_id is not None:
            params["after_id"] = after_id

        async with httpx.AsyncClient() as client:
            url = f"{BASE_URL}/groups/{group_id}/messages"
            request_params = {"token": self.api_token, **params}
            log.debug("Sending request to GroupMe", method=HTTPMethod.GET, url=url)
            response = await client.get(url, params=request_params, timeout=10)
        log.debug("Received GroupMe response", status=response.status_code, url=str(response.url))

        if response.status_code == 304:
            return []

        response.raise_for_status()
        data = response.json()["response"]

        if not isinstance(data, dict):
            raise TypeError

        messages = data["messages"]

        if not isinstance(messages, list):
            raise TypeError

        return [Message.model_validate(m) for m in messages]
