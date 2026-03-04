from sophia.services.inventory import InventoryService
from sophia.services.mcp.adapter import MCPServiceAdapter
from sophia.services.mcp.client import MCPClient
from sophia.services.models import ProductDetails, ProductStock, WarrantyStatus


class MCPInventoryService(InventoryService):
    def __init__(self, client: MCPClient, tool_mapping: dict):
        self.adapter = MCPServiceAdapter(client, tool_mapping)

    async def check_stock(self, product_id: str | None = None) -> list[ProductStock]:
        return await self.adapter._call("check_stock", product_id=product_id)

    async def get_product_details(self, product_id: str) -> ProductDetails | None:
        return await self.adapter._call("get_product_details", product_id=product_id)

    async def check_warranty_status(
        self, order_id: str, product_id: str
    ) -> WarrantyStatus:
        return await self.adapter._call(
            "check_warranty_status", order_id=order_id, product_id=product_id
        )
