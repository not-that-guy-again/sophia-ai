from dataclasses import asdict

from sophia.services.models import ReturnItem
from sophia.tools.base import Tool, ToolResult


class InitiateReturnTool(Tool):
    name = "initiate_return"
    description = "Initiate a return for items from a delivered order."
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order to return items from"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string"},
                        "quantity": {"type": "integer"},
                        "reason": {
                            "type": "string",
                            "enum": [
                                "defective",
                                "wrong_item",
                                "not_as_described",
                                "changed_mind",
                            ],
                        },
                    },
                    "required": ["product_id", "quantity", "reason"],
                },
            },
            "reason": {"type": "string", "description": "Overall return reason"},
        },
        "required": ["order_id", "items", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = None  # Variable based on order value

    def inject_services(self, services):
        self.compensation_service = services.get("compensation")

    async def execute(self, params: dict) -> ToolResult:
        items = [
            ReturnItem(
                product_id=i["product_id"],
                quantity=i["quantity"],
                reason=i["reason"],
            )
            for i in params["items"]
        ]
        try:
            result = await self.compensation_service.initiate_return(
                params["order_id"],
                items,
                params["reason"],
            )
        except ValueError as e:
            return ToolResult(success=False, data=None, message=str(e))

        return ToolResult(
            success=True,
            data=asdict(result),
            message=f"Return {result.return_id} initiated for order {params['order_id']}",
        )


class CheckReturnStatusTool(Tool):
    name = "check_return_status"
    description = "Check the status of an existing return."
    parameters = {
        "type": "object",
        "properties": {
            "return_id": {"type": "string", "description": "Return ID to check"},
        },
        "required": ["return_id"],
    }
    authority_level = "agent"
    max_financial_impact = None

    def inject_services(self, services):
        self.compensation_service = services.get("compensation")

    async def execute(self, params: dict) -> ToolResult:
        status = await self.compensation_service.check_return_status(params["return_id"])
        if not status:
            return ToolResult(
                success=False,
                data=None,
                message=f"Return {params['return_id']} not found",
            )
        return ToolResult(
            success=True,
            data=asdict(status),
            message=f"Return {status.return_id}: {status.status}",
        )
