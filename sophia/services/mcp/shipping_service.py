from sophia.services.mcp.adapter import MCPServiceAdapter
from sophia.services.mcp.client import MCPClient
from sophia.services.models import (
    Address,
    AddressUpdateResult,
    ReturnLabel,
    ShipmentTracking,
    ShippingOption,
)
from sophia.services.shipping import ShippingService


class MCPShippingService(ShippingService):
    def __init__(self, client: MCPClient, tool_mapping: dict):
        self.adapter = MCPServiceAdapter(client, tool_mapping)

    async def track_shipment(self, order_id: str) -> ShipmentTracking | None:
        return await self.adapter._call("track_shipment", order_id=order_id)

    async def get_shipping_options(self, order_id: str) -> list[ShippingOption]:
        return await self.adapter._call("get_shipping_options", order_id=order_id)

    async def update_shipping_address(
        self, order_id: str, new_address: Address
    ) -> AddressUpdateResult:
        return await self.adapter._call(
            "update_shipping_address", order_id=order_id, new_address=new_address
        )

    async def generate_return_label(
        self, order_id: str, reason: str
    ) -> ReturnLabel:
        return await self.adapter._call(
            "generate_return_label", order_id=order_id, reason=reason
        )
