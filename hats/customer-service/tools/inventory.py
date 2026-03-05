from dataclasses import asdict

from sophia.tools.base import Tool, ToolResult


class CheckCurrentInventoryTool(Tool):
    name = "check_current_inventory"
    description = (
        "Check current inventory levels. "
        "Pass a product_id for a specific product, or omit for full inventory."
    )
    parameters = {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "Specific product ID to check, or omit for full inventory",
            },
        },
        "required": [],
    }
    authority_level = "agent"
    max_financial_impact = None
    risk_floor = None

    def inject_services(self, services):
        self.inventory_service = services.get("inventory")

    async def execute(self, params: dict) -> ToolResult:
        product_id = params.get("product_id")
        stocks = await self.inventory_service.check_stock(product_id)

        if product_id and not stocks:
            return ToolResult(success=False, data=None, message=f"Product {product_id} not found")

        products = [asdict(s) for s in stocks]
        if product_id:
            msg = f"Inventory for {stocks[0].name}: {stocks[0].quantity_available} available"
        else:
            msg = f"Full inventory: {len(products)} products"
        return ToolResult(success=True, data={"products": products}, message=msg)
