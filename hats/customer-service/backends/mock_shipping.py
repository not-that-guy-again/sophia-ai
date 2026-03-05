import uuid
from datetime import datetime, timedelta

from sophia.services.models import (
    Address,
    AddressUpdateResult,
    ReturnLabel,
    ShipmentTracking,
    ShippingOption,
)
from sophia.services.shipping import ShippingService

from .mock_data import MockDataStore


class MockShippingService(ShippingService):
    async def track_shipment(self, order_id: str) -> ShipmentTracking | None:
        return MockDataStore.shipments.get(order_id)

    async def get_shipping_options(self, order_id: str) -> list[ShippingOption]:
        return [
            ShippingOption("UPS", "Ground", 5, 9.99),
            ShippingOption("UPS", "2-Day", 2, 19.99),
            ShippingOption("FedEx", "Overnight", 1, 29.99),
        ]

    async def update_shipping_address(
        self, order_id: str, new_address: Address
    ) -> AddressUpdateResult:
        order = MockDataStore.orders.get(order_id)
        if not order:
            return AddressUpdateResult(
                order_id=order_id, success=False, failure_reason="Order not found"
            )

        if order.status not in ("pending", "confirmed", "processing"):
            return AddressUpdateResult(
                order_id=order_id,
                success=False,
                failure_reason=f"Cannot update address for order in '{order.status}' status",
            )

        order.shipping_address = new_address
        order.updated_at = datetime.now()
        return AddressUpdateResult(order_id=order_id, success=True, new_address=new_address)

    async def generate_return_label(self, order_id: str, reason: str) -> ReturnLabel:
        order = MockDataStore.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        return ReturnLabel(
            label_url=f"https://labels.example.com/{uuid.uuid4().hex[:8]}",
            carrier="UPS",
            tracking_number=f"1Z{uuid.uuid4().hex[:12].upper()}",
            expiry=datetime.now() + timedelta(days=14),
        )
