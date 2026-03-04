"""Tests for MCPCommunicationService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from sophia.services.communication import (
    CommunicationContact,
    CommunicationMessage,
)
from sophia.services.mcp.communication_service import MCPCommunicationService
from sophia.services.mcp.models import MCPToolResult


def _make_policy(**contacts):
    """Build a policy dict from keyword args like manager=("slack", "#chan")."""
    return {
        role: CommunicationContact(role=role, channel=channel, address=address)
        for role, (channel, address) in contacts.items()
    }


def _mock_client():
    client = MagicMock()
    client.connect = AsyncMock()
    client.call_tool = AsyncMock()
    return client


def _msg(subject="Test", body="body", priority="medium"):
    return CommunicationMessage(subject=subject, body=body, priority=priority)


async def test_slack_channel_routes_to_slack_client():
    slack = _mock_client()
    slack.call_tool.return_value = MCPToolResult(
        content=[{"type": "text", "text": '{"ok": true, "ts": "123.456"}'}],
        is_error=False,
    )
    policy = _make_policy(manager=("slack", "#escalations"))
    service = MCPCommunicationService(
        slack_client=slack, gmail_client=None, policy=policy
    )

    result = await service.send_to_role("manager", _msg())
    assert result.success is True
    assert result.channel == "slack"
    assert result.message_id == "123.456"
    slack.call_tool.assert_called_once()
    call_args = slack.call_tool.call_args
    assert call_args[0][0] == "slack_post_message"
    assert call_args[0][1]["channel_id"] == "#escalations"


async def test_email_channel_routes_to_gmail_client():
    gmail = _mock_client()
    gmail.call_tool.return_value = MCPToolResult(
        content=[{"type": "text", "text": '{"messageId": "abc123"}'}],
        is_error=False,
    )
    policy = _make_policy(supervisor=("email", "sup@example.com"))
    service = MCPCommunicationService(
        slack_client=None, gmail_client=gmail, policy=policy
    )

    result = await service.send_to_role("supervisor", _msg())
    assert result.success is True
    assert result.channel == "email"
    assert result.message_id == "abc123"
    gmail.call_tool.assert_called_once()
    call_args = gmail.call_tool.call_args
    assert call_args[0][0] == "send_email"
    assert call_args[0][1]["to"] == ["sup@example.com"]


async def test_unknown_role_returns_failure():
    policy = _make_policy(manager=("slack", "#chan"))
    service = MCPCommunicationService(
        slack_client=_mock_client(), gmail_client=None, policy=policy
    )

    result = await service.send_to_role("nonexistent", _msg())
    assert result.success is False
    assert "not found" in result.failure_reason


async def test_empty_address_returns_failure():
    policy = _make_policy(supervisor=("email", ""))
    service = MCPCommunicationService(
        slack_client=None, gmail_client=_mock_client(), policy=policy
    )

    result = await service.send_to_role("supervisor", _msg())
    assert result.success is False
    assert "no address" in result.failure_reason.lower()


async def test_unconfigured_slack_channel_raises():
    policy = _make_policy(manager=("slack", "#chan"))
    service = MCPCommunicationService(
        slack_client=None, gmail_client=None, policy=policy
    )

    with pytest.raises(ValueError, match="Slack"):
        await service.send_to_role("manager", _msg())


async def test_unconfigured_email_channel_raises():
    policy = _make_policy(supervisor=("email", "sup@example.com"))
    service = MCPCommunicationService(
        slack_client=None, gmail_client=None, policy=policy
    )

    with pytest.raises(ValueError, match="Gmail"):
        await service.send_to_role("supervisor", _msg())


async def test_source_ticket_appended_to_slack_message():
    slack = _mock_client()
    slack.call_tool.return_value = MCPToolResult(
        content=[{"type": "text", "text": '{"ok": true, "ts": "1.2"}'}],
        is_error=False,
    )
    policy = _make_policy(manager=("slack", "#chan"))
    service = MCPCommunicationService(
        slack_client=slack, gmail_client=None, policy=policy
    )

    msg = CommunicationMessage(
        subject="Test", body="body", priority="high", source_ticket="TKT-123"
    )
    await service.send_to_role("manager", msg)
    text = slack.call_tool.call_args[0][1]["text"]
    assert "TKT-123" in text


async def test_get_contacts_returns_policy():
    policy = _make_policy(
        manager=("slack", "#chan"), team=("slack", "#team")
    )
    service = MCPCommunicationService(
        slack_client=None, gmail_client=None, policy=policy
    )
    contacts = await service.get_contacts()
    assert len(contacts) == 2
    roles = {c.role for c in contacts}
    assert roles == {"manager", "team"}
