from dataclasses import asdict

from sophia.tools.base import Tool, ToolResult


class LookUpProductTool(Tool):
    name = "look_up_product"
    description = "Look up detailed product information by product ID."
    parameters = {
        "type": "object",
        "properties": {
            "product_id": {"type": "string", "description": "Product ID to look up"},
        },
        "required": ["product_id"],
    }
    authority_level = "agent"
    max_financial_impact = None

    def inject_services(self, services):
        self.inventory_service = services.get("inventory")

    async def execute(self, params: dict) -> ToolResult:
        details = await self.inventory_service.get_product_details(params["product_id"])
        if not details:
            return ToolResult(
                success=False,
                data=None,
                message=f"Product {params['product_id']} not found",
            )
        return ToolResult(
            success=True,
            data=asdict(details),
            message=f"Found product: {details.name}",
        )


class CheckWarrantyStatusTool(Tool):
    name = "check_warranty_status"
    description = "Check the warranty status for a product in a specific order."
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "Order containing the product",
            },
            "product_id": {
                "type": "string",
                "description": "Product to check warranty for",
            },
        },
        "required": ["order_id", "product_id"],
    }
    authority_level = "agent"
    max_financial_impact = None

    def inject_services(self, services):
        self.inventory_service = services.get("inventory")

    async def execute(self, params: dict) -> ToolResult:
        try:
            ws = await self.inventory_service.check_warranty_status(
                params["order_id"],
                params["product_id"],
            )
        except ValueError as e:
            return ToolResult(success=False, data=None, message=str(e))

        status_msg = "active" if ws.is_active else "expired"
        return ToolResult(
            success=True,
            data=asdict(ws),
            message=f"Warranty for {params['product_id']}: {status_msg} ({ws.coverage_type})",
        )
