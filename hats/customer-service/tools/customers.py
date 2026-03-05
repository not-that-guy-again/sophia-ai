from dataclasses import asdict

from sophia.tools.base import Tool, ToolResult


class LookUpCustomerTool(Tool):
    name = "look_up_customer"
    description = "Search for a customer by email, phone, or name."
    parameters = {
        "type": "object",
        "properties": {
            "email": {"type": "string", "description": "Customer email address"},
            "phone": {"type": "string", "description": "Customer phone number"},
            "name": {"type": "string", "description": "Customer name (partial match)"},
        },
        "required": [],
    }
    authority_level = "agent"
    max_financial_impact = None
    risk_floor = None

    def inject_services(self, services):
        self.customer_service = services.get("customer")

    async def execute(self, params: dict) -> ToolResult:
        email = params.get("email")
        phone = params.get("phone")
        name = params.get("name")

        if not any([email, phone, name]):
            return ToolResult(
                success=False,
                data=None,
                message="At least one search parameter (email, phone, or name) is required",
            )

        query = email or phone or name
        customers = await self.customer_service.search_customers(query)
        if not customers:
            return ToolResult(
                success=False,
                data=None,
                message=f"No customers found matching '{query}'",
            )
        return ToolResult(
            success=True,
            data={"customers": [asdict(c) for c in customers]},
            message=f"Found {len(customers)} customer(s)",
        )


class GetCustomerOrderHistoryTool(Tool):
    name = "get_customer_order_history"
    description = "Get a customer's full order history, returns, and compensation."
    parameters = {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "Customer ID"},
        },
        "required": ["customer_id"],
    }
    authority_level = "agent"
    max_financial_impact = None
    risk_floor = None

    def inject_services(self, services):
        self.customer_service = services.get("customer")

    async def execute(self, params: dict) -> ToolResult:
        try:
            history = await self.customer_service.get_customer_history(params["customer_id"])
        except ValueError as e:
            return ToolResult(success=False, data=None, message=str(e))

        return ToolResult(
            success=True,
            data=asdict(history),
            message=(
                f"History for {history.customer.name}: "
                f"{len(history.orders)} orders, {len(history.returns)} returns"
            ),
        )
