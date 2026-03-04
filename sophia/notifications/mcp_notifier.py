"""MCP-backed notification service for customer outbound emails."""

import json
import logging

from sophia.services.mcp.client import MCPClient
from sophia.services.notification import (
    NotificationMessage,
    NotificationRecipient,
    NotificationResult,
    NotificationService,
)

logger = logging.getLogger(__name__)


class MCPNotificationService(NotificationService):
    def __init__(self, client: MCPClient, channel: str = "email"):
        self.client = client
        self.channel = channel
        self._connected = False

    async def _ensure_connected(self) -> None:
        if not self._connected:
            await self.client.connect()
            self._connected = True

    async def send_notification(
        self,
        recipient: NotificationRecipient,
        message: NotificationMessage,
    ) -> NotificationResult:
        if self.channel != "email":
            raise NotImplementedError(
                f"Channel '{self.channel}' is not yet supported. "
                f"Only 'email' is currently implemented."
            )

        if not recipient.email:
            return NotificationResult(
                success=False,
                channel=self.channel,
                failure_reason="Recipient has no email address",
            )

        await self._ensure_connected()

        args = {
            "to": [recipient.email],
            "subject": message.subject or "(no subject)",
            "body": message.body,
            "content_type": "text/plain",
        }

        try:
            result = await self.client.call_tool("send_email", args)
        except Exception as exc:
            logger.exception("MCP notification send failed")
            return NotificationResult(
                success=False,
                channel=self.channel,
                failure_reason=str(exc),
            )

        if result.is_error:
            error_text = self._extract_text(result.content)
            return NotificationResult(
                success=False,
                channel=self.channel,
                failure_reason=error_text or "MCP tool returned an error",
            )

        response = self._parse_json_content(result.content)
        message_id = response.get("messageId")
        if message_id:
            return NotificationResult(
                success=True,
                channel=self.channel,
                message_id=message_id,
            )

        return NotificationResult(
            success=False,
            channel=self.channel,
            failure_reason="Gmail MCP did not return a messageId",
        )

    async def get_channels(self) -> list[str]:
        return [self.channel]

    @classmethod
    def from_config(cls, config: dict) -> "MCPNotificationService":
        client = MCPClient(
            server_url=config["server_url"],
            server_name=config.get("server_name", "gmail-mcp"),
            auth_headers={"Authorization": f"Bearer {config['auth_token']}"}
            if config.get("auth_token")
            else None,
        )
        return cls(client=client, channel=config.get("channel", "email"))

    @staticmethod
    def _parse_json_content(content: list) -> dict:
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, KeyError):
                    continue
        return {}

    @staticmethod
    def _extract_text(content: list) -> str:
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
