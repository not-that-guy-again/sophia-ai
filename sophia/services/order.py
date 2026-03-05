from abc import ABC, abstractmethod

from sophia.services.models import (
    CancellationResult,
    Order,
    OrderChanges,
    OrderItem,
    OrderStatus,
)


class OrderService(ABC):
    @abstractmethod
    async def get_order(self, order_id: str) -> Order | None: ...

    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderStatus | None: ...

    @abstractmethod
    async def search_orders_by_customer(self, customer_id: str, limit: int = 20) -> list[Order]: ...

    @abstractmethod
    async def cancel_order(self, order_id: str, reason: str) -> CancellationResult: ...

    @abstractmethod
    async def update_order(self, order_id: str, changes: OrderChanges) -> Order: ...

    @abstractmethod
    async def place_order(self, customer_id: str, items: list[OrderItem]) -> Order: ...
