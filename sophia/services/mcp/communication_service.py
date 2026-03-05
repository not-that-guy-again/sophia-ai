"""MCP-backed communication service for internal team messaging."""

import json
import logging

from sophia.services.communication import (
    CommunicationContact,
    CommunicationMessage,
    CommunicationResult,
    CommunicationService,
)
from sophia.services.mcp.client import MCPClient

logger = logging.getLogger(__name__)


class MCPCommunicationService(CommunicationService):
    def __init__(
        self,
        slack_client: MCPClient | None,
        gmail_client: MCPClient | None,
        policy: dict[str, CommunicationContact],
    ):
        self.slack_client = slack_client
        self.gmail_client = gmail_client
        self.policy = policy  # role -> CommunicationContact
        self._slack_connected = False
        self._gmail_connected = False

    async def _ensure_slack_connected(self) -> None:
        if not self._slack_connected and self.slack_client:
            await self.slack_client.connect()
            self._slack_connected = True

    async def _ensure_gmail_connected(self) -> None:
        if not self._gmail_connected and self.gmail_client:
            await self.gmail_client.connect()
            self._gmail_connected = True

    async def send_to_role(self, role: str, message: CommunicationMessage) -> CommunicationResult:
        contact = self.policy.get(role)
        if not contact:
            return CommunicationResult(
                success=False,
                channel="none",
                failure_reason=(
                    f"Role '{role}' not found in communications policy. "
                    f"Add it to constraints.json under communications_policy.contacts."
                ),
            )

        if not contact.address:
            return CommunicationResult(
                success=False,
                channel=contact.channel,
                failure_reason=(
                    f"Contact '{role}' has no address configured. "
                    f"Set the address in constraints.json."
                ),
            )

        if contact.channel == "slack":
            if not self.slack_client:
                return CommunicationResult(
                    success=False,
                    channel="slack",
                    failure_reason=(
                        "Slack channel is referenced in policy but no Slack MCP "
                        "is configured in hat.json communications.channels.slack"
                    ),
                )
            return await self._send_slack(contact, message)

        elif contact.channel == "email":
            if not self.gmail_client:
                return CommunicationResult(
                    success=False,
                    channel="email",
                    failure_reason=(
                        "Email channel is referenced in policy but no Gmail MCP "
                        "is configured in hat.json communications.channels.email"
                    ),
                )
            return await self._send_email(contact, message)

        else:
            raise ValueError(f"Unknown channel: {contact.channel!r}")

    async def _send_slack(
        self, contact: CommunicationContact, message: CommunicationMessage
    ) -> CommunicationResult:
        await self._ensure_slack_connected()

        text = f"*[{message.priority.upper()}]* {message.subject}\n\n{message.body}"
        if message.source_ticket:
            text += f"\n\nTicket: {message.source_ticket}"

        args = {
            "channel_id": contact.address,
            "text": text,
            "content_type": "text/markdown",
        }

        try:
            result = await self.slack_client.call_tool("slack_post_message", args)
        except Exception as exc:
            logger.exception("Slack MCP call failed")
            return CommunicationResult(
                success=False,
                channel="slack",
                failure_reason=str(exc),
            )

        if result.is_error:
            error_text = self._extract_text(result.content)
            return CommunicationResult(
                success=False,
                channel="slack",
                failure_reason=error_text or "Slack MCP returned an error",
            )

        response = self._parse_json_content(result.content)
        if response.get("ok"):
            return CommunicationResult(
                success=True,
                channel="slack",
                message_id=response.get("ts"),
            )

        return CommunicationResult(
            success=False,
            channel="slack",
            failure_reason=response.get("error", "Unknown Slack error"),
        )

    async def _send_email(
        self, contact: CommunicationContact, message: CommunicationMessage
    ) -> CommunicationResult:
        await self._ensure_gmail_connected()

        body = message.body
        if message.source_ticket:
            body += f"\n\nSource ticket: {message.source_ticket}"

        args = {
            "to": [contact.address],
            "subject": f"[{message.priority.upper()}] {message.subject}",
            "body": body,
            "content_type": "text/plain",
        }

        try:
            result = await self.gmail_client.call_tool("send_email", args)
        except Exception as exc:
            logger.exception("Gmail MCP call failed")
            return CommunicationResult(
                success=False,
                channel="email",
                failure_reason=str(exc),
            )

        if result.is_error:
            error_text = self._extract_text(result.content)
            return CommunicationResult(
                success=False,
                channel="email",
                failure_reason=error_text or "Gmail MCP returned an error",
            )

        response = self._parse_json_content(result.content)
        if response.get("messageId"):
            return CommunicationResult(
                success=True,
                channel="email",
                message_id=response["messageId"],
            )

        return CommunicationResult(
            success=False,
            channel="email",
            failure_reason="Gmail MCP did not return a messageId",
        )

    async def get_contacts(self) -> list[CommunicationContact]:
        return list(self.policy.values())

    @staticmethod
    def _parse_json_content(content: list) -> dict:
        """Extract JSON from MCP tool result content blocks."""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                try:
                    return json.loads(block["text"])
                except (json.JSONDecodeError, KeyError):
                    continue
        return {}

    @staticmethod
    def _extract_text(content: list) -> str:
        """Extract plain text from MCP tool result content blocks."""
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts)
