"""Tests for framework communication tools."""

from unittest.mock import AsyncMock

from sophia.services.communication import (
    CommunicationContact,
    CommunicationResult,
)
from sophia.services.mock.communication import MockCommunicationService
from sophia.tools.communication import (
    EscalateToHumanTool,
    NotifyManagerTool,
    RequestApprovalTool,
)


def _real_service(send_result=None):
    """Build a non-mock CommunicationService with a stubbed send_to_role."""
    from sophia.services.mcp.communication_service import MCPCommunicationService

    service = MCPCommunicationService(
        slack_client=None,
        gmail_client=None,
        policy={
            "manager": CommunicationContact(
                role="manager", channel="slack", address="#test"
            ),
        },
    )
    if send_result is None:
        send_result = CommunicationResult(
            success=True, channel="slack", message_id="ts-123"
        )
    service.send_to_role = AsyncMock(return_value=send_result)
    return service


async def test_notify_manager_sends_to_manager_role():
    service = MockCommunicationService()
    tool = NotifyManagerTool()
    tool.inject_communication(service)

    result = await tool.execute({
        "reason": "Customer upset",
        "priority": "high",
        "context_summary": "Details here",
    })

    assert result.success is True
    assert result.data["channel"] == "mock"
    assert len(service._sent) == 1
    role, msg = service._sent[0]
    assert role == "manager"
    assert "Customer upset" in msg.subject


async def test_notify_manager_no_service():
    tool = NotifyManagerTool()
    result = await tool.execute({
        "reason": "test",
        "priority": "low",
        "context_summary": "test",
    })
    assert result.success is False
    assert "not configured" in result.message


async def test_request_approval_sends_to_supervisor():
    service = MockCommunicationService()
    tool = RequestApprovalTool()
    tool.inject_communication(service)

    result = await tool.execute({
        "action_description": "Refund $500",
        "risk_level": "high",
        "recommended_action": "Approve refund",
    })

    assert result.success is True
    assert len(service._sent) == 1
    role, msg = service._sent[0]
    assert role == "supervisor"


async def test_escalate_returns_success_with_mock_notification_false():
    service = MockCommunicationService()
    tool = EscalateToHumanTool()
    tool.inject_communication(service)

    result = await tool.execute({
        "reason": "Customer wants manager",
        "priority": "high",
        "context_summary": "Escalation needed",
    })

    assert result.success is True
    assert result.data["notification_sent"] is False
    assert "ticket_id" in result.data


async def test_escalate_returns_success_with_real_notification_true():
    service = _real_service()
    tool = EscalateToHumanTool()
    tool.inject_communication(service)

    result = await tool.execute({
        "reason": "Customer wants manager",
        "priority": "urgent",
        "context_summary": "Escalation needed",
    })

    assert result.success is True
    assert result.data["notification_sent"] is True
    service.send_to_role.assert_called_once()


async def test_escalate_success_even_when_notification_fails():
    service = _real_service(
        send_result=CommunicationResult(
            success=False, channel="slack", failure_reason="channel not found"
        )
    )
    tool = EscalateToHumanTool()
    tool.inject_communication(service)

    result = await tool.execute({
        "reason": "test",
        "priority": "medium",
        "context_summary": "test",
    })

    assert result.success is True
    assert result.data["notification_sent"] is False


async def test_escalate_no_service():
    tool = EscalateToHumanTool()
    result = await tool.execute({
        "reason": "test",
        "priority": "low",
        "context_summary": "test",
    })
    assert result.success is True
    assert result.data["notification_sent"] is False
    assert "ticket_id" in result.data
