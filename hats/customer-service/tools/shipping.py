from dataclasses import asdict

from sophia.services.models import Address
from sophia.tools.base import Tool, ToolResult


class TrackShipmentTool(Tool):
    name = "track_shipment"
    description = "Track the shipment status for an order."
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order to track"},
        },
        "required": ["order_id"],
    }
    authority_level = "agent"
    max_financial_impact = None

    def inject_services(self, services):
        self.shipping_service = services.get("shipping")

    async def execute(self, params: dict) -> ToolResult:
        tracking = await self.shipping_service.track_shipment(params["order_id"])
        if not tracking:
            return ToolResult(
                success=False,
                data=None,
                message=f"No shipment tracking found for order {params['order_id']}",
            )
        return ToolResult(
            success=True,
            data=asdict(tracking),
            message=f"Shipment {tracking.tracking_number}: {tracking.status}",
        )


class UpdateShippingAddressTool(Tool):
    name = "update_shipping_address"
    description = "Update the shipping address for an unshipped order."
    parameters = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order to update"},
            "line1": {"type": "string"},
            "line2": {"type": "string"},
            "city": {"type": "string"},
            "state": {"type": "string"},
            "postal_code": {"type": "string"},
            "country": {"type": "string", "default": "US"},
        },
        "required": ["order_id", "line1", "city", "state", "postal_code"],
    }
    authority_level = "agent"
    max_financial_impact = None

    def inject_services(self, services):
        self.shipping_service = services.get("shipping")

    async def execute(self, params: dict) -> ToolResult:
        new_address = Address(
            line1=params["line1"],
            city=params["city"],
            state=params["state"],
            postal_code=params["postal_code"],
            line2=params.get("line2"),
            country=params.get("country", "US"),
        )
        result = await self.shipping_service.update_shipping_address(
            params["order_id"],
            new_address,
        )
        if not result.success:
            return ToolResult(
                success=False,
                data=None,
                message=result.failure_reason or "Address update failed",
            )
        return ToolResult(
            success=True,
            data=asdict(result),
            message=f"Shipping address updated for order {params['order_id']}",
        )
