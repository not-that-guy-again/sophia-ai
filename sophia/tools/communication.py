"""Framework-level communication tools.

These tools are provided by the framework, not the hat. The hat controls
whether they appear (via its tools list) and who they reach (via
communications_policy in constraints.json). The framework handles the
actual sending.
"""

import uuid

from sophia.services.communication import (
    CommunicationMessage,
    CommunicationService,
)
from sophia.services.mock.communication import MockCommunicationService
from sophia.tools.base import Tool, ToolResult


class NotifyManagerTool(Tool):
    name = "notify_manager"
    description = (
        "Send a notification to the manager about a situation that "
        "requires their awareness but not necessarily immediate action."
    )
    parameters = {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why the manager is being notified",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "urgent"],
                "description": "Notification priority level",
            },
            "context_summary": {
                "type": "string",
                "description": "Summary of the situation for the manager",
            },
        },
        "required": ["reason", "priority", "context_summary"],
    }
    authority_level = "agent"
    _communication_service: CommunicationService | None = None

    def inject_communication(self, service: CommunicationService) -> None:
        self._communication_service = service

    async def execute(self, params: dict) -> ToolResult:
        if not self._communication_service:
            return ToolResult(
                success=False,
                data=None,
                message="Communication service not configured.",
            )
        message = CommunicationMessage(
            subject=f"Notification: {params['reason']}",
            body=params.get("context_summary", ""),
            priority=params.get("priority", "medium"),
        )
        result = await self._communication_service.send_to_role(
            "manager", message
        )
        return ToolResult(
            success=result.success,
            data={"channel": result.channel, "message_id": result.message_id},
            message=result.failure_reason or f"Message sent via {result.channel}",
        )


class RequestApprovalTool(Tool):
    name = "request_approval"
    description = (
        "Request approval from a supervisor for an action that exceeds "
        "the agent's authority level."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action_description": {
                "type": "string",
                "description": "What action needs approval",
            },
            "risk_level": {
                "type": "string",
                "description": "Assessed risk level of the action",
            },
            "recommended_action": {
                "type": "string",
                "description": "What the agent recommends doing",
            },
        },
        "required": ["action_description", "risk_level", "recommended_action"],
    }
    authority_level = "agent"
    _communication_service: CommunicationService | None = None

    def inject_communication(self, service: CommunicationService) -> None:
        self._communication_service = service

    async def execute(self, params: dict) -> ToolResult:
        if not self._communication_service:
            return ToolResult(
                success=False,
                data=None,
                message="Communication service not configured.",
            )
        message = CommunicationMessage(
            subject=f"Approval Required: {params['action_description']}",
            body=(
                f"Risk Level: {params.get('risk_level', 'unknown')}\n\n"
                f"Recommended Action: {params.get('recommended_action', 'N/A')}"
            ),
            priority="high",
        )
        result = await self._communication_service.send_to_role(
            "supervisor", message
        )
        return ToolResult(
            success=result.success,
            data={"channel": result.channel, "message_id": result.message_id},
            message=result.failure_reason or f"Approval request sent via {result.channel}",
        )


class EscalateToHumanTool(Tool):
    name = "escalate_to_human"
    description = (
        "Escalate the conversation to a human agent when the request "
        "exceeds automated handling."
    )
    parameters = {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why this needs human attention",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "urgent"],
                "description": "Escalation priority level",
            },
            "context_summary": {
                "type": "string",
                "description": "Summary of the conversation for the human agent",
            },
        },
        "required": ["reason", "priority", "context_summary"],
    }
    authority_level = "agent"
    _communication_service: CommunicationService | None = None

    def inject_communication(self, service: CommunicationService) -> None:
        self._communication_service = service

    async def execute(self, params: dict) -> ToolResult:
        priority = params.get("priority", "medium")
        ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        queue_positions = {"low": 8, "medium": 4, "high": 2, "urgent": 1}
        wait_times = {
            "low": "~30 min",
            "medium": "~15 min",
            "high": "~5 min",
            "urgent": "~2 min",
        }

        notification_sent = False

        # Attempt notification if service is available and not mock
        if (
            self._communication_service
            and not isinstance(self._communication_service, MockCommunicationService)
        ):
            message = CommunicationMessage(
                subject=f"Escalation: {params['reason']}",
                body=params.get("context_summary", ""),
                priority=priority,
                source_ticket=ticket_id,
            )
            result = await self._communication_service.send_to_role(
                "manager", message
            )
            notification_sent = result.success

        return ToolResult(
            success=True,
            data={
                "ticket_id": ticket_id,
                "queue_position": queue_positions.get(priority, 4),
                "estimated_wait": wait_times.get(priority, "~15 min"),
                "notification_sent": notification_sent,
            },
            message=f"Escalated to human agent (priority: {priority})",
        )
