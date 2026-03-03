import uuid

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
            "customer_id": {"type": "string", "description": "Customer to receive the discount"},
            "discount_percent": {"type": "integer", "description": "Discount percentage (max 20 for agent)"},
            "reason": {"type": "string", "description": "Reason for offering the discount"},
        },
        "required": ["customer_id", "discount_percent", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = None  # Depends on future purchase

    async def execute(self, params: dict) -> ToolResult:
        pct = params.get("discount_percent", 0)
        return ToolResult(
            success=True,
            data={
                "discount_code": f"DISC-{uuid.uuid4().hex[:8].upper()}",
                "percent": pct,
                "expiry": "2025-04-01",
            },
            message=f"Generated {pct}% discount code for customer {params.get('customer_id')}",
        )


class OfferFreeShippingTool(Tool):
    name = "offer_free_shipping"
    description = "Offer free shipping to a customer on a specific or next order."
    parameters = {
        "type": "object",
        "properties": {
            "customer_id": {"type": "string", "description": "Customer to receive free shipping"},
            "order_id": {"type": "string", "description": "Specific order ID, or omit for next order"},
            "reason": {"type": "string", "description": "Reason for offering free shipping"},
        },
        "required": ["customer_id", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = 15.00

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(
            success=True,
            data={
                "applied": True,
                "estimated_savings": 9.99,
            },
            message=f"Free shipping applied for customer {params.get('customer_id')}",
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
            "order_id": {"type": "string", "description": "The order to partially refund"},
            "amount": {"type": "number", "description": "Dollar amount to refund (max $50 for agent)"},
            "reason": {"type": "string", "description": "Reason for the partial refund"},
        },
        "required": ["order_id", "amount", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = 50.00

    async def execute(self, params: dict) -> ToolResult:
        amount = params.get("amount", 0)
        return ToolResult(
            success=True,
            data={
                "refund_id": f"REF-{uuid.uuid4().hex[:8].upper()}",
                "amount": amount,
                "status": "processed",
            },
            message=f"Partial refund of ${amount:.2f} issued for order {params.get('order_id')}",
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
            "order_id": {"type": "string", "description": "The order to fully refund"},
            "reason": {"type": "string", "description": "Reason for the full refund"},
        },
        "required": ["order_id", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = 100.00

    async def execute(self, params: dict) -> ToolResult:
        # In a real system, would look up order total
        return ToolResult(
            success=True,
            data={
                "refund_id": f"REF-{uuid.uuid4().hex[:8].upper()}",
                "amount": 0.00,  # Would be the actual order total
                "status": "processed",
            },
            message=f"Full refund issued for order {params.get('order_id')}",
        )


class SendReplacementProductTool(Tool):
    name = "send_replacement_product"
    description = "Send a replacement product for a defective or missing item."
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Original order ID"},
            "product_id": {"type": "string", "description": "Product to send as replacement"},
            "reason": {"type": "string", "description": "Reason for the replacement"},
        },
        "required": ["order_id", "product_id", "reason"],
    }
    authority_level = "agent"
    max_financial_impact = None  # Depends on product

    async def execute(self, params: dict) -> ToolResult:
        return ToolResult(
            success=True,
            data={
                "replacement_order_id": f"ORD-RPL-{uuid.uuid4().hex[:6].upper()}",
                "estimated_delivery": "2025-03-08",
            },
            message=f"Replacement product shipped for order {params.get('order_id')}",
        )
