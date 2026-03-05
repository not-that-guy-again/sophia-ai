from datetime import datetime

from sophia.services.models import (
    CancellationResult,
    Order,
    OrderChanges,
    OrderItem,
    OrderStatus,
)
from sophia.services.order import OrderService

from .mock_data import MockDataStore


class MockOrderService(OrderService):
    async def get_order(self, order_id: str) -> Order | None:
        return MockDataStore.orders.get(order_id)

    async def get_order_status(self, order_id: str) -> OrderStatus | None:
        order = MockDataStore.orders.get(order_id)
        if not order:
            return None
        return OrderStatus(
            order_id=order.order_id,
            status=order.status,
            last_updated=order.updated_at,
            estimated_delivery=(
                MockDataStore.shipments[order_id].estimated_delivery
                if order_id in MockDataStore.shipments
                else None
            ),
            tracking_number=order.tracking_number,
        )

    async def search_orders_by_customer(self, customer_id: str, limit: int = 20) -> list[Order]:
        results = [o for o in MockDataStore.orders.values() if o.customer_id == customer_id]
        results.sort(key=lambda o: o.created_at, reverse=True)
        return results[:limit]

    async def cancel_order(self, order_id: str, reason: str) -> CancellationResult:
        order = MockDataStore.orders.get(order_id)
        if not order:
            return CancellationResult(order_id=order_id, success=False, reason="Order not found")

        if order.status in ("shipped", "delivered", "cancelled"):
            return CancellationResult(
                order_id=order_id,
                success=False,
                reason=f"Cannot cancel order in '{order.status}' status",
            )

        order.status = "cancelled"
        order.updated_at = datetime.now()
        return CancellationResult(
            order_id=order_id,
            success=True,
            refund_amount=order.total,
        )

    async def update_order(self, order_id: str, changes: OrderChanges) -> Order:
        order = MockDataStore.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        if changes.shipping_address:
            order.shipping_address = changes.shipping_address
        order.updated_at = datetime.now()
        return order

    async def place_order(self, customer_id: str, items: list[OrderItem]) -> Order:
        MockDataStore._next_order_id += 1
        order_id = f"ORD-{MockDataStore._next_order_id}"
        total = sum(item.total_price for item in items)

        order = Order(
            order_id=order_id,
            customer_id=customer_id,
            status="pending",
            items=items,
            total=total,
            currency="USD",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        MockDataStore.orders[order_id] = order
        return order
