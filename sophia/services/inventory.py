from abc import ABC, abstractmethod

from sophia.services.models import ProductDetails, ProductStock, WarrantyStatus


class InventoryService(ABC):
    @abstractmethod
    async def check_stock(self, product_id: str | None = None) -> list[ProductStock]: ...

    @abstractmethod
    async def get_product_details(self, product_id: str) -> ProductDetails | None: ...

    @abstractmethod
    async def check_warranty_status(
        self, order_id: str, product_id: str
    ) -> WarrantyStatus: ...
