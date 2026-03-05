from datetime import timedelta

from sophia.services.inventory import InventoryService
from sophia.services.models import ProductDetails, ProductStock, WarrantyStatus

from .mock_data import MockDataStore


class MockInventoryService(InventoryService):
    async def check_stock(self, product_id: str | None = None) -> list[ProductStock]:
        if product_id:
            stock = MockDataStore.inventory.get(product_id)
            return [stock] if stock else []
        return list(MockDataStore.inventory.values())

    async def get_product_details(self, product_id: str) -> ProductDetails | None:
        return MockDataStore.products.get(product_id)

    async def check_warranty_status(self, order_id: str, product_id: str) -> WarrantyStatus:
        order = MockDataStore.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        product = MockDataStore.products.get(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        # Check that the product was in this order
        if not any(item.product_id == product_id for item in order.items):
            raise ValueError(f"Product {product_id} not found in order {order_id}")

        purchase_date = order.created_at
        warranty_months = product.warranty_months
        warranty_expiry = purchase_date + timedelta(days=warranty_months * 30)
        from datetime import datetime

        is_active = datetime.now() < warranty_expiry

        return WarrantyStatus(
            order_id=order_id,
            product_id=product_id,
            purchase_date=purchase_date,
            warranty_expiry=warranty_expiry,
            is_active=is_active,
            coverage_type="standard",
        )
