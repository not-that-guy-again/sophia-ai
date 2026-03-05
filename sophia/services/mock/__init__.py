"""Mock service implementations backed by a centralized in-memory data store.

Used as the default "mock" provider in the ServiceRegistry. Provides
functional logic (not just hardcoded returns) for testing and demos.
"""

import uuid
from datetime import datetime, timedelta

from sophia.services.compensation import CompensationService
from sophia.services.customer import CustomerService
from sophia.services.inventory import InventoryService
from sophia.services.models import (
    Address,
    AddressUpdateResult,
    CancellationResult,
    CouponParams,
    CouponResult,
    Customer,
    CustomerHistory,
    DiscountResult,
    FreeShippingResult,
    Order,
    OrderChanges,
    OrderItem,
    OrderStatus,
    ProductDetails,
    ProductStock,
    RefundResult,
    ReturnInitiationResult,
    ReturnItem,
    ReturnLabel,
    ReturnStatus,
    ShipmentTracking,
    ShippingOption,
    TrackingEvent,
    WarrantyStatus,
)
from sophia.services.order import OrderService
from sophia.services.shipping import ShippingService

NOW = datetime(2025, 3, 1, 12, 0, 0)


class MockDataStore:
    """Shared in-memory data for all mock services."""

    customers: dict[str, Customer] = {
        "CUST-001": Customer(
            "CUST-001",
            "jane.smith@example.com",
            "Jane Smith",
            "555-0101",
            NOW - timedelta(days=365),
            3,
            250.96,
            ["loyal"],
        ),
        "CUST-002": Customer(
            "CUST-002",
            "john.doe@example.com",
            "John Doe",
            "555-0102",
            NOW - timedelta(days=180),
            1,
            499.99,
        ),
        "CUST-003": Customer(
            "CUST-003",
            "alice.johnson@example.com",
            "Alice Johnson",
            "555-0103",
            NOW - timedelta(days=90),
            2,
            90.00,
        ),
        "CUST-004": Customer(
            "CUST-004",
            "bob.williams@example.com",
            "Bob Williams",
            None,
            NOW - timedelta(days=30),
            1,
            129.99,
        ),
        "CUST-005": Customer(
            "CUST-005",
            "carol.davis@example.com",
            "Carol Davis",
            "555-0105",
            NOW - timedelta(days=14),
            1,
            79.99,
        ),
    }

    orders: dict[str, Order] = {
        "ORD-12345": Order(
            "ORD-12345",
            "CUST-001",
            "delivered",
            [
                OrderItem("PROD-001", "Wireless Headphones", 1, 79.99, 79.99),
                OrderItem("PROD-002", "USB-C Cable", 2, 12.99, 25.98),
            ],
            105.97,
            "USD",
            NOW - timedelta(days=14),
            NOW - timedelta(days=7),
            Address("123 Main St", "Springfield", "IL", "62701"),
            "1Z999AA10123456784",
        ),
        "ORD-67890": Order(
            "ORD-67890",
            "CUST-002",
            "processing",
            [OrderItem("PROD-003", "PlayStation 5", 1, 499.99, 499.99)],
            499.99,
            "USD",
            NOW - timedelta(days=1),
            NOW - timedelta(hours=6),
        ),
        "ORD-11111": Order(
            "ORD-11111",
            "CUST-003",
            "shipped",
            [OrderItem("PROD-004", "Laptop Stand", 1, 45.00, 45.00)],
            45.00,
            "USD",
            NOW - timedelta(days=3),
            NOW - timedelta(days=1),
            Address("456 Oak Ave", "Chicago", "IL", "60601"),
            "1Z999AA10123456785",
        ),
        "ORD-22222": Order(
            "ORD-22222",
            "CUST-003",
            "delivered",
            [OrderItem("PROD-004", "Laptop Stand", 1, 45.00, 45.00)],
            45.00,
            "USD",
            NOW - timedelta(days=45),
            NOW - timedelta(days=40),
            Address("456 Oak Ave", "Chicago", "IL", "60601"),
            "1Z999AA10123456786",
        ),
        "ORD-33333": Order(
            "ORD-33333",
            "CUST-001",
            "pending",
            [OrderItem("PROD-005", "Mechanical Keyboard", 1, 129.99, 129.99)],
            129.99,
            "USD",
            NOW - timedelta(hours=2),
            NOW - timedelta(hours=2),
        ),
        "ORD-44444": Order(
            "ORD-44444",
            "CUST-004",
            "confirmed",
            [OrderItem("PROD-005", "Mechanical Keyboard", 1, 129.99, 129.99)],
            129.99,
            "USD",
            NOW - timedelta(hours=12),
            NOW - timedelta(hours=10),
            Address("789 Pine Rd", "Austin", "TX", "73301"),
        ),
        "ORD-55555": Order(
            "ORD-55555",
            "CUST-005",
            "cancelled",
            [OrderItem("PROD-001", "Wireless Headphones", 1, 79.99, 79.99)],
            79.99,
            "USD",
            NOW - timedelta(days=10),
            NOW - timedelta(days=9),
        ),
        "ORD-66666": Order(
            "ORD-66666",
            "CUST-001",
            "delivered",
            [OrderItem("PROD-002", "USB-C Cable", 1, 12.99, 12.99)],
            12.99,
            "USD",
            NOW - timedelta(days=60),
            NOW - timedelta(days=55),
        ),
        "ORD-77777": Order(
            "ORD-77777",
            "CUST-005",
            "shipped",
            [OrderItem("PROD-001", "Wireless Headphones", 1, 79.99, 79.99)],
            79.99,
            "USD",
            NOW - timedelta(days=5),
            NOW - timedelta(days=3),
            Address("321 Elm St", "Denver", "CO", "80201"),
            "1Z999AA10123456787",
        ),
        "ORD-88888": Order(
            "ORD-88888",
            "CUST-002",
            "delivered",
            [OrderItem("PROD-002", "USB-C Cable", 3, 12.99, 38.97)],
            38.97,
            "USD",
            NOW - timedelta(days=20),
            NOW - timedelta(days=15),
        ),
    }

    products: dict[str, ProductDetails] = {
        "PROD-001": ProductDetails(
            "PROD-001",
            "Wireless Headphones",
            "Premium noise-cancelling wireless headphones with 30-hour battery",
            79.99,
            "Audio",
            {"battery_hours": 30, "noise_cancelling": True},
            12,
        ),
        "PROD-002": ProductDetails(
            "PROD-002",
            "USB-C Cable",
            "Braided USB-C to USB-C cable, 6ft, 100W PD",
            12.99,
            "Accessories",
            {"length_ft": 6, "power_delivery_w": 100},
            6,
        ),
        "PROD-003": ProductDetails(
            "PROD-003",
            "PlayStation 5",
            "Sony PlayStation 5 console, disc edition",
            499.99,
            "Gaming",
            {"storage_gb": 825, "edition": "disc"},
            12,
        ),
        "PROD-004": ProductDetails(
            "PROD-004",
            "Laptop Stand",
            "Adjustable aluminum laptop stand, fits 10-17 inch laptops",
            45.00,
            "Accessories",
            {"material": "aluminum", "max_size_inches": 17},
            24,
        ),
        "PROD-005": ProductDetails(
            "PROD-005",
            "Mechanical Keyboard",
            "RGB mechanical keyboard with Cherry MX Blue switches",
            129.99,
            "Peripherals",
            {"switch_type": "Cherry MX Blue", "rgb": True},
            24,
        ),
    }

    inventory: dict[str, ProductStock] = {
        "PROD-001": ProductStock("PROD-001", "Wireless Headphones", 150, 79.99),
        "PROD-002": ProductStock("PROD-002", "USB-C Cable", 500, 12.99),
        "PROD-003": ProductStock("PROD-003", "PlayStation 5", 5, 499.99),
        "PROD-004": ProductStock("PROD-004", "Laptop Stand", 75, 45.00),
        "PROD-005": ProductStock("PROD-005", "Mechanical Keyboard", 200, 129.99),
    }

    shipments: dict[str, ShipmentTracking] = {
        "ORD-12345": ShipmentTracking(
            "ORD-12345",
            "UPS",
            "1Z999AA10123456784",
            "delivered",
            NOW - timedelta(days=7),
            "Springfield, IL",
            [
                TrackingEvent(NOW - timedelta(days=12), "Chicago, IL", "Picked up", "picked_up"),
                TrackingEvent(
                    NOW - timedelta(days=10), "Indianapolis, IN", "In transit", "in_transit"
                ),
                TrackingEvent(NOW - timedelta(days=7), "Springfield, IL", "Delivered", "delivered"),
            ],
        ),
        "ORD-11111": ShipmentTracking(
            "ORD-11111",
            "FedEx",
            "1Z999AA10123456785",
            "in_transit",
            NOW + timedelta(days=2),
            "St. Louis, MO",
            [
                TrackingEvent(NOW - timedelta(days=1), "Memphis, TN", "Picked up", "picked_up"),
                TrackingEvent(
                    NOW - timedelta(hours=8), "St. Louis, MO", "In transit", "in_transit"
                ),
            ],
        ),
        "ORD-77777": ShipmentTracking(
            "ORD-77777",
            "USPS",
            "1Z999AA10123456787",
            "in_transit",
            NOW + timedelta(days=1),
            "Kansas City, MO",
            [
                TrackingEvent(NOW - timedelta(days=3), "Houston, TX", "Picked up", "picked_up"),
                TrackingEvent(
                    NOW - timedelta(days=1), "Kansas City, MO", "In transit", "in_transit"
                ),
            ],
        ),
    }

    returns: dict[str, ReturnStatus] = {
        "RET-001": ReturnStatus(
            "RET-001",
            "ORD-22222",
            "processed",
            [ReturnItem("PROD-004", 1, "changed_mind")],
            NOW - timedelta(days=30),
            45.00,
        ),
        "RET-002": ReturnStatus(
            "RET-002",
            "ORD-66666",
            "in_transit",
            [ReturnItem("PROD-002", 1, "defective")],
            NOW - timedelta(days=2),
        ),
    }

    _next_order_id: int = 99000
    _next_return_id: int = 100
    _next_refund_id: int = 100


# ---------------------------------------------------------------------------
# Mock service implementations
# ---------------------------------------------------------------------------


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
        return CancellationResult(order_id=order_id, success=True, refund_amount=order.total)

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


class MockCustomerService(CustomerService):
    async def get_customer(self, customer_id: str) -> Customer | None:
        return MockDataStore.customers.get(customer_id)

    async def search_customers(self, query: str) -> list[Customer]:
        q = query.lower()
        return [
            c
            for c in MockDataStore.customers.values()
            if q in c.name.lower() or q in c.email.lower() or (c.phone and q in c.phone)
        ]

    async def get_customer_history(self, customer_id: str) -> CustomerHistory:
        customer = MockDataStore.customers.get(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        orders = sorted(
            [o for o in MockDataStore.orders.values() if o.customer_id == customer_id],
            key=lambda o: o.created_at,
            reverse=True,
        )
        returns = [
            r
            for r in MockDataStore.returns.values()
            if any(
                o.customer_id == customer_id
                for o in MockDataStore.orders.values()
                if o.order_id == r.order_id
            )
        ]
        total_refunded = sum(r.refund_amount or 0.0 for r in returns)
        return CustomerHistory(
            customer=customer,
            orders=orders,
            returns=returns,
            total_refunded=total_refunded,
        )


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
        if not any(item.product_id == product_id for item in order.items):
            raise ValueError(f"Product {product_id} not found in order {order_id}")
        purchase_date = order.created_at
        warranty_expiry = purchase_date + timedelta(days=product.warranty_months * 30)
        is_active = NOW < warranty_expiry
        return WarrantyStatus(
            order_id=order_id,
            product_id=product_id,
            purchase_date=purchase_date,
            warranty_expiry=warranty_expiry,
            is_active=is_active,
            coverage_type="standard",
        )


class MockCompensationService(CompensationService):
    async def apply_discount(self, customer_id: str, percent: int, reason: str) -> DiscountResult:
        customer = MockDataStore.customers.get(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        return DiscountResult(
            discount_code=f"DISC-{uuid.uuid4().hex[:8].upper()}",
            percent=percent,
            expiry=datetime.now() + timedelta(days=30),
            customer_id=customer_id,
        )

    async def process_partial_refund(
        self, order_id: str, amount: float, reason: str
    ) -> RefundResult:
        order = MockDataStore.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if amount > order.total:
            raise ValueError(f"Refund amount ${amount:.2f} exceeds order total ${order.total:.2f}")
        return RefundResult(
            refund_id=f"REF-{uuid.uuid4().hex[:8].upper()}",
            order_id=order_id,
            amount=amount,
            status="processed",
            method="original_payment",
        )

    async def process_full_refund(self, order_id: str, reason: str) -> RefundResult:
        order = MockDataStore.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        return RefundResult(
            refund_id=f"REF-{uuid.uuid4().hex[:8].upper()}",
            order_id=order_id,
            amount=order.total,
            status="processed",
            method="original_payment",
        )

    async def apply_free_shipping(
        self, customer_id: str, order_id: str | None, reason: str
    ) -> FreeShippingResult:
        customer = MockDataStore.customers.get(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        return FreeShippingResult(applied=True, customer_id=customer_id, estimated_savings=9.99)

    async def generate_coupon(self, customer_id: str, params: CouponParams) -> CouponResult:
        customer = MockDataStore.customers.get(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")
        return CouponResult(
            coupon_code=f"COUP-{uuid.uuid4().hex[:8].upper()}",
            type=params.type,
            value=params.value,
            expiry=datetime.now() + timedelta(days=params.expiry_days),
            customer_id=customer_id,
        )

    async def initiate_return(
        self, order_id: str, items: list[ReturnItem], reason: str
    ) -> ReturnInitiationResult:
        order = MockDataStore.orders.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        if order.status != "delivered":
            raise ValueError(f"Cannot initiate return for order in '{order.status}' status")
        # Use NOW for consistent mock behavior with fixed dates
        days_since_delivery = (NOW - order.updated_at).days
        if days_since_delivery > 30:
            raise ValueError("Return window (30 days from delivery) has expired")
        existing = [
            r
            for r in MockDataStore.returns.values()
            if r.order_id == order_id and r.status not in ("processed", "cancelled")
        ]
        if existing:
            raise ValueError(f"Order {order_id} already has an active return")

        MockDataStore._next_return_id += 1
        return_id = f"RET-{MockDataStore._next_return_id:03d}"
        has_defective = any(
            i.reason in ("defective", "wrong_item", "not_as_described") for i in items
        )
        label_url = f"https://labels.example.com/{uuid.uuid4().hex[:8]}" if has_defective else None
        ret = ReturnStatus(
            return_id=return_id,
            order_id=order_id,
            status="initiated",
            items=items,
            created_at=datetime.now(),
        )
        MockDataStore.returns[return_id] = ret
        instructions = (
            "Ship items back using the provided label."
            if has_defective
            else "Ship items back at your expense. Include the return ID on the package."
        )
        return ReturnInitiationResult(
            return_id=return_id,
            order_id=order_id,
            return_label_url=label_url,
            status="initiated",
            instructions=instructions,
        )

    async def check_return_status(self, return_id: str) -> ReturnStatus | None:
        return MockDataStore.returns.get(return_id)
