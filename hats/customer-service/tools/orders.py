from sophia.tools.base import Tool, ToolResult

# Mock order database
MOCK_ORDERS = {
    "ORD-12345": {
        "order_id": "ORD-12345",
        "customer_name": "Jane Smith",
        "customer_id": "CUST-001",
        "items": [
            {"name": "Wireless Headphones", "quantity": 1, "price": 79.99},
            {"name": "USB-C Cable", "quantity": 2, "price": 12.99},
        ],
        "total": 105.97,
        "status": "delivered",
        "date": "2025-02-15",
    },
    "ORD-67890": {
        "order_id": "ORD-67890",
        "customer_name": "John Doe",
        "customer_id": "CUST-002",
        "items": [
            {"name": "PlayStation 5", "quantity": 1, "price": 499.99},
        ],
        "total": 499.99,
        "status": "processing",
        "date": "2025-03-01",
    },
    "ORD-11111": {
        "order_id": "ORD-11111",
        "customer_name": "Alice Johnson",
        "customer_id": "CUST-003",
        "items": [
            {"name": "Laptop Stand", "quantity": 1, "price": 45.00},
        ],
        "total": 45.00,
        "status": "shipped",
        "date": "2025-02-28",
        "tracking_number": "1Z999AA10123456784",
        "estimated_delivery": "2025-03-05",
    },
}


class LookUpOrderTool(Tool):
    name = "look_up_order"
    description = "Look up full order details including items, total, and status."
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "The order ID to look up"},
        },
        "required": ["order_id"],
    }
    authority_level = "agent"
    max_financial_impact = None

    async def execute(self, params: dict) -> ToolResult:
        order_id = params.get("order_id", "").upper()
        # Normalize — accept "12345", "#12345", "ORD-12345"
        if not order_id.startswith("ORD-"):
            order_id = f"ORD-{order_id.lstrip('#')}"

        order = MOCK_ORDERS.get(order_id)
        if order:
            return ToolResult(success=True, data=order, message=f"Found order {order_id}")
        return ToolResult(
            success=False, data=None, message=f"Order {order_id} not found"
        )


class CheckOrderStatusTool(Tool):
    name = "check_order_status"
    description = "Check the current status and tracking info for an order."
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "The order ID to check"},
        },
        "required": ["order_id"],
    }
    authority_level = "agent"
    max_financial_impact = None

    async def execute(self, params: dict) -> ToolResult:
        order_id = params.get("order_id", "").upper()
        if not order_id.startswith("ORD-"):
            order_id = f"ORD-{order_id.lstrip('#')}"

        order = MOCK_ORDERS.get(order_id)
        if not order:
            return ToolResult(
                success=False, data=None, message=f"Order {order_id} not found"
            )

        status_data = {
            "order_id": order["order_id"],
            "status": order["status"],
            "tracking_number": order.get("tracking_number"),
            "estimated_delivery": order.get("estimated_delivery"),
        }
        return ToolResult(
            success=True, data=status_data, message=f"Status for {order_id}: {order['status']}"
        )


class PlaceNewOrderTool(Tool):
    name = "place_new_order"
    description = "Place a new order for a customer."
    parameters = {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "The customer placing the order"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string"},
                        "quantity": {"type": "integer"},
                    },
                },
                "description": "Items to order",
            },
        },
        "required": ["customer_id", "items"],
    }
    authority_level = "agent"
    max_financial_impact = None  # Variable based on items

    async def execute(self, params: dict) -> ToolResult:
        # Mock: just generate a fake order
        return ToolResult(
            success=True,
            data={
                "order_id": "ORD-99999",
                "total": 0.00,  # Would be calculated from actual inventory
                "estimated_delivery": "2025-03-10",
            },
            message="New order placed successfully",
        )
