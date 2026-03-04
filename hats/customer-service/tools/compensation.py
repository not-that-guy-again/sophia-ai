from dataclasses import asdict

from sophia.tools.base import Tool, ToolResult


class OfferDiscountTool(Tool):
    name = "offer_discount"
    description = (
        "Offer a percentage discount to a customer. "
        "Agent can offer up to 20%. Anything higher requires supervisor authority."
    )
    parameters = {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "Customer to receive the discount",
            },
            "discount_percent": {
                "type": "integer",
                "description": "Discount percentage (max 20 for agent)",
            },
            "reason": {
                "type": "string",
                "description": "Reason for offering the discount",
            },
        },
        "required": ["customer_id", "discount_percent", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = None

    def inject_services(self, services):
        self.compensation_service = services.get("compensation")

    async def execute(self, params: dict) -> ToolResult:
        result = await self.compensation_service.apply_discount(
            params["customer_id"], params["discount_percent"], params["reason"],
        )
        return ToolResult(
            success=True,
            data=asdict(result),
            message=(
                f"Generated {result.percent}% discount code for customer "
                f"{params['customer_id']}"
            ),
        )


class OfferFreeShippingTool(Tool):
    name = "offer_free_shipping"
    description = "Offer free shipping to a customer on a specific or next order."
    parameters = {
        "type": "object",
        "properties": {
            "customer_id": {
                "type": "string",
                "description": "Customer to receive free shipping",
            },
            "order_id": {
                "type": "string",
                "description": "Specific order ID, or omit for next order",
            },
            "reason": {
                "type": "string",
                "description": "Reason for offering free shipping",
            },
        },
        "required": ["customer_id", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = 15.00

    def inject_services(self, services):
        self.compensation_service = services.get("compensation")

    async def execute(self, params: dict) -> ToolResult:
        result = await self.compensation_service.apply_free_shipping(
            params["customer_id"], params.get("order_id"), params["reason"],
        )
        return ToolResult(
            success=True,
            data=asdict(result),
            message=f"Free shipping applied for customer {params['customer_id']}",
        )


class OfferPartialRefundTool(Tool):
    name = "offer_partial_refund"
    description = (
        "Issue a partial refund on an order. "
        "Agent can refund up to $50. Higher amounts require supervisor approval."
    )
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order to partially refund",
            },
            "amount": {
                "type": "number",
                "description": "Dollar amount to refund (max $50 for agent)",
            },
            "reason": {
                "type": "string",
                "description": "Reason for the partial refund",
            },
        },
        "required": ["order_id", "amount", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = 50.00

    def inject_services(self, services):
        self.compensation_service = services.get("compensation")

    async def execute(self, params: dict) -> ToolResult:
        result = await self.compensation_service.process_partial_refund(
            params["order_id"], params["amount"], params["reason"],
        )
        return ToolResult(
            success=True,
            data=asdict(result),
            message=(
                f"Partial refund of ${result.amount:.2f} issued for order "
                f"{params['order_id']}"
            ),
        )


class OfferFullRefundTool(Tool):
    name = "offer_full_refund"
    description = (
        "Issue a full refund on an order. "
        "Agent can refund orders up to $100. Higher-value orders require supervisor approval."
    )
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "The order to fully refund",
            },
            "reason": {
                "type": "string",
                "description": "Reason for the full refund",
            },
        },
        "required": ["order_id", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = 100.00

    def inject_services(self, services):
        self.compensation_service = services.get("compensation")

    async def execute(self, params: dict) -> ToolResult:
        result = await self.compensation_service.process_full_refund(
            params["order_id"], params["reason"],
        )
        return ToolResult(
            success=True,
            data=asdict(result),
            message=f"Full refund issued for order {params['order_id']}",
        )


class SendReplacementProductTool(Tool):
    name = "send_replacement_product"
    description = "Send a replacement product for a defective or missing item."
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {
                "type": "string",
                "description": "Original order ID",
            },
            "product_id": {
                "type": "string",
                "description": "Product to send as replacement",
            },
            "reason": {
                "type": "string",
                "description": "Reason for the replacement",
            },
        },
        "required": ["order_id", "product_id", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = None

    def inject_services(self, services):
        self.order_service = services.get("order")
        self.inventory_service = services.get("inventory")

    async def execute(self, params: dict) -> ToolResult:
        from sophia.services.models import OrderItem

        product = await self.inventory_service.get_product_details(params["product_id"])
        if not product:
            return ToolResult(
                success=False, data=None,
                message=f"Product {params['product_id']} not found",
            )

        items = [OrderItem(
            product_id=product.product_id,
            name=product.name,
            quantity=1,
            unit_price=0.0,
            total_price=0.0,
        )]
        order = await self.order_service.place_order(
            params.get("customer_id", "REPLACEMENT"), items,
        )
        return ToolResult(
            success=True,
            data={"replacement_order_id": order.order_id},
            message=f"Replacement product shipped for order {params['order_id']}",
        )
