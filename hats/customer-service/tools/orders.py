from dataclasses import asdict

from sophia.services.models import OrderItem
from sophia.tools.base import Tool, ToolResult


def _normalize_order_id(raw: str) -> str:
    order_id = raw.upper()
    if not order_id.startswith("ORD-"):
        order_id = f"ORD-{order_id.lstrip('#')}"
    return order_id


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

    def inject_services(self, services):
        self.order_service = services.get("order")

    async def execute(self, params: dict) -> ToolResult:
        order_id = _normalize_order_id(params.get("order_id", ""))
        order = await self.order_service.get_order(order_id)
        if not order:
            return ToolResult(success=False, data=None, message=f"Order {order_id} not found")
        return ToolResult(success=True, data=asdict(order), message=f"Found order {order_id}")


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

    def inject_services(self, services):
        self.order_service = services.get("order")

    async def execute(self, params: dict) -> ToolResult:
        order_id = _normalize_order_id(params.get("order_id", ""))
        status = await self.order_service.get_order_status(order_id)
        if not status:
            return ToolResult(success=False, data=None, message=f"Order {order_id} not found")
        return ToolResult(
            success=True,
            data=asdict(status),
            message=f"Status for {order_id}: {status.status}",
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
    max_financial_impact = None

    def inject_services(self, services):
        self.order_service = services.get("order")
        self.inventory_service = services.get("inventory")

    async def execute(self, params: dict) -> ToolResult:
        customer_id = params.get("customer_id", "")
        raw_items = params.get("items", [])

        order_items = []
        for item in raw_items:
            product_id = item.get("product_id", "")
            quantity = item.get("quantity", 1)
            details = await self.inventory_service.get_product_details(product_id)
            if not details:
                return ToolResult(
                    success=False, data=None,
                    message=f"Product {product_id} not found",
                )
            order_items.append(OrderItem(
                product_id=product_id,
                name=details.name,
                quantity=quantity,
                unit_price=details.price,
                total_price=details.price * quantity,
            ))

        order = await self.order_service.place_order(customer_id, order_items)
        return ToolResult(
            success=True,
            data=asdict(order),
            message="New order placed successfully",
        )


class CancelOrderTool(Tool):
    name = "cancel_order"
    description = "Cancel an order. Only works for unshipped orders."
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order to cancel"},
            "reason": {"type": "string", "description": "Reason for cancellation"},
        },
        "required": ["order_id", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = None  # Variable based on order value

    def inject_services(self, services):
        self.order_service = services.get("order")

    async def execute(self, params: dict) -> ToolResult:
        order_id = _normalize_order_id(params.get("order_id", ""))
        result = await self.order_service.cancel_order(order_id, params["reason"])
        if not result.success:
            return ToolResult(
                success=False, data=None,
                message=result.reason or f"Cannot cancel order {order_id}",
            )
        return ToolResult(
            success=True,
            data=asdict(result),
            message=f"Order {order_id} cancelled. Refund: ${result.refund_amount:.2f}",
        )
