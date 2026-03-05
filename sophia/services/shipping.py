from abc import ABC, abstractmethod

from sophia.services.models import (
    Address,
    AddressUpdateResult,
    ReturnLabel,
    ShipmentTracking,
    ShippingOption,
)


class ShippingService(ABC):
    @abstractmethod
    async def track_shipment(self, order_id: str) -> ShipmentTracking | None: ...

    @abstractmethod
    async def get_shipping_options(self, order_id: str) -> list[ShippingOption]: ...

    @abstractmethod
    async def update_shipping_address(
        self, order_id: str, new_address: Address
    ) -> AddressUpdateResult: ...

    @abstractmethod
    async def generate_return_label(self, order_id: str, reason: str) -> ReturnLabel: ...
