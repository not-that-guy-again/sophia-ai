import uuid

from sophia.tools.base import Tool, ToolResult


class EscalateToHumanTool(Tool):
    name = "escalate_to_human"
    description = (
        "Escalate the conversation to a human agent when the request exceeds automated handling."
    )
    parameters = {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why this needs human attention"},
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
    max_financial_impact = None
    risk_floor = None

    async def execute(self, params: dict) -> ToolResult:
        priority = params.get("priority", "medium")
        queue_positions = {"low": 8, "medium": 4, "high": 2, "urgent": 1}
        wait_times = {"low": "~30 min", "medium": "~15 min", "high": "~5 min", "urgent": "~2 min"}

        return ToolResult(
            success=True,
            data={
                "ticket_id": f"TKT-{uuid.uuid4().hex[:8].upper()}",
                "queue_position": queue_positions.get(priority, 4),
                "estimated_wait": wait_times.get(priority, "~15 min"),
            },
            message=f"Escalated to human agent (priority: {priority})",
        )
