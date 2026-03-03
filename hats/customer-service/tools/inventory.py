from sophia.tools.base import Tool, ToolResult

MOCK_INVENTORY = {
    "PROD-001": {"product_id": "PROD-001", "name": "Wireless Headphones", "quantity_available": 150, "price": 79.99},
    "PROD-002": {"product_id": "PROD-002", "name": "USB-C Cable", "quantity_available": 500, "price": 12.99},
    "PROD-003": {"product_id": "PROD-003", "name": "PlayStation 5", "quantity_available": 5, "price": 499.99},
    "PROD-004": {"product_id": "PROD-004", "name": "Laptop Stand", "quantity_available": 75, "price": 45.00},
    "PROD-005": {"product_id": "PROD-005", "name": "Mechanical Keyboard", "quantity_available": 200, "price": 129.99},
}


class CheckCurrentInventoryTool(Tool):
    name = "check_current_inventory"
    description = "Check current inventory levels. Pass a product_id for a specific product, or omit for full inventory."
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

    async def execute(self, params: dict) -> ToolResult:
        product_id = params.get("product_id")

        if product_id:
            product = MOCK_INVENTORY.get(product_id)
            if product:
                return ToolResult(
                    success=True,
                    data={"products": [product]},
                    message=f"Inventory for {product['name']}: {product['quantity_available']} available",
                )
            return ToolResult(
                success=False, data=None, message=f"Product {product_id} not found"
            )

        return ToolResult(
            success=True,
            data={"products": list(MOCK_INVENTORY.values())},
            message=f"Full inventory: {len(MOCK_INVENTORY)} products",
        )
