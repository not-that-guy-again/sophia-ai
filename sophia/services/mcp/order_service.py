from sophia.services.mcp.adapter import MCPServiceAdapter
from sophia.services.mcp.client import MCPClient
from sophia.services.models import (
    CancellationResult,
    Order,
    OrderChanges,
    OrderItem,
    OrderStatus,
)
from sophia.services.order import OrderService


class MCPOrderService(OrderService):
    def __init__(self, client: MCPClient, tool_mapping: dict):
        self.adapter = MCPServiceAdapter(client, tool_mapping)

    async def get_order(self, order_id: str) -> Order | None:
        return await self.adapter._call("get_order", order_id=order_id)

    async def get_order_status(self, order_id: str) -> OrderStatus | None:
        return await self.adapter._call("get_order_status", order_id=order_id)

    async def search_orders_by_customer(
        self, customer_id: str, limit: int = 20
    ) -> list[Order]:
        return await self.adapter._call(
            "search_orders_by_customer", customer_id=customer_id, limit=limit
        )

    async def cancel_order(self, order_id: str, reason: str) -> CancellationResult:
        return await self.adapter._call(
            "cancel_order", order_id=order_id, reason=reason
        )

    async def update_order(self, order_id: str, changes: OrderChanges) -> Order:
        return await self.adapter._call(
            "update_order", order_id=order_id, changes=changes
        )

    async def place_order(self, customer_id: str, items: list[OrderItem]) -> Order:
        return await self.adapter._call(
            "place_order", customer_id=customer_id, items=items
        )
