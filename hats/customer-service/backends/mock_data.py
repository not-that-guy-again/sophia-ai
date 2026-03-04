"""Centralized mock data store for all mock backend services.

All mock services operate on this shared data so changes are consistent
across services (e.g., cancelling an order updates both order and customer data).
"""

from datetime import datetime, timedelta

from sophia.services.models import (
    Address,
    Customer,
    Order,
    OrderItem,
    ProductDetails,
    ProductStock,
    ReturnItem,
    ReturnStatus,
    ShipmentTracking,
    TrackingEvent,
)

NOW = datetime(2025, 3, 1, 12, 0, 0)


class MockDataStore:
    """Shared in-memory data for all mock services."""

    customers: dict[str, Customer] = {
        "CUST-001": Customer(
            customer_id="CUST-001",
            email="jane.smith@example.com",
            name="Jane Smith",
            phone="555-0101",
            created_at=NOW - timedelta(days=365),
            total_orders=3,
            total_spent=250.96,
            tags=["loyal"],
        ),
        "CUST-002": Customer(
            customer_id="CUST-002",
            email="john.doe@example.com",
            name="John Doe",
            phone="555-0102",
            created_at=NOW - timedelta(days=180),
            total_orders=1,
            total_spent=499.99,
        ),
        "CUST-003": Customer(
            customer_id="CUST-003",
            email="alice.johnson@example.com",
            name="Alice Johnson",
            phone="555-0103",
            created_at=NOW - timedelta(days=90),
            total_orders=2,
            total_spent=90.00,
        ),
        "CUST-004": Customer(
            customer_id="CUST-004",
            email="bob.williams@example.com",
            name="Bob Williams",
            created_at=NOW - timedelta(days=30),
            total_orders=1,
            total_spent=129.99,
        ),
        "CUST-005": Customer(
            customer_id="CUST-005",
            email="carol.davis@example.com",
            name="Carol Davis",
            phone="555-0105",
            created_at=NOW - timedelta(days=14),
            total_orders=1,
            total_spent=79.99,
        ),
    }

    orders: dict[str, Order] = {
        "ORD-12345": Order(
            order_id="ORD-12345",
            customer_id="CUST-001",
            status="delivered",
            items=[
                OrderItem("PROD-001", "Wireless Headphones", 1, 79.99, 79.99),
                OrderItem("PROD-002", "USB-C Cable", 2, 12.99, 25.98),
            ],
            total=105.97,
            currency="USD",
            created_at=NOW - timedelta(days=14),
            updated_at=NOW - timedelta(days=7),
            tracking_number="1Z999AA10123456784",
            shipping_address=Address("123 Main St", "Springfield", "IL", "62701"),
        ),
        "ORD-67890": Order(
            order_id="ORD-67890",
            customer_id="CUST-002",
            status="processing",
            items=[
                OrderItem("PROD-003", "PlayStation 5", 1, 499.99, 499.99),
            ],
            total=499.99,
            currency="USD",
            created_at=NOW - timedelta(days=1),
            updated_at=NOW - timedelta(hours=6),
        ),
        "ORD-11111": Order(
            order_id="ORD-11111",
            customer_id="CUST-003",
            status="shipped",
            items=[
                OrderItem("PROD-004", "Laptop Stand", 1, 45.00, 45.00),
            ],
            total=45.00,
            currency="USD",
            created_at=NOW - timedelta(days=3),
            updated_at=NOW - timedelta(days=1),
            tracking_number="1Z999AA10123456785",
            shipping_address=Address("456 Oak Ave", "Chicago", "IL", "60601"),
        ),
        "ORD-22222": Order(
            order_id="ORD-22222",
            customer_id="CUST-003",
            status="delivered",
            items=[
                OrderItem("PROD-004", "Laptop Stand", 1, 45.00, 45.00),
            ],
            total=45.00,
            currency="USD",
            created_at=NOW - timedelta(days=45),
            updated_at=NOW - timedelta(days=40),
            tracking_number="1Z999AA10123456786",
            shipping_address=Address("456 Oak Ave", "Chicago", "IL", "60601"),
        ),
        "ORD-33333": Order(
            order_id="ORD-33333",
            customer_id="CUST-001",
            status="pending",
            items=[
                OrderItem("PROD-005", "Mechanical Keyboard", 1, 129.99, 129.99),
            ],
            total=129.99,
            currency="USD",
            created_at=NOW - timedelta(hours=2),
            updated_at=NOW - timedelta(hours=2),
        ),
        "ORD-44444": Order(
            order_id="ORD-44444",
            customer_id="CUST-004",
            status="confirmed",
            items=[
                OrderItem("PROD-005", "Mechanical Keyboard", 1, 129.99, 129.99),
            ],
            total=129.99,
            currency="USD",
            created_at=NOW - timedelta(hours=12),
            updated_at=NOW - timedelta(hours=10),
            shipping_address=Address("789 Pine Rd", "Austin", "TX", "73301"),
        ),
        "ORD-55555": Order(
            order_id="ORD-55555",
            customer_id="CUST-005",
            status="cancelled",
            items=[
                OrderItem("PROD-001", "Wireless Headphones", 1, 79.99, 79.99),
            ],
            total=79.99,
            currency="USD",
            created_at=NOW - timedelta(days=10),
            updated_at=NOW - timedelta(days=9),
        ),
        "ORD-66666": Order(
            order_id="ORD-66666",
            customer_id="CUST-001",
            status="delivered",
            items=[
                OrderItem("PROD-002", "USB-C Cable", 1, 12.99, 12.99),
            ],
            total=12.99,
            currency="USD",
            created_at=NOW - timedelta(days=60),
            updated_at=NOW - timedelta(days=55),
        ),
        "ORD-77777": Order(
            order_id="ORD-77777",
            customer_id="CUST-005",
            status="shipped",
            items=[
                OrderItem("PROD-001", "Wireless Headphones", 1, 79.99, 79.99),
            ],
            total=79.99,
            currency="USD",
            created_at=NOW - timedelta(days=5),
            updated_at=NOW - timedelta(days=3),
            tracking_number="1Z999AA10123456787",
            shipping_address=Address("321 Elm St", "Denver", "CO", "80201"),
        ),
        "ORD-88888": Order(
            order_id="ORD-88888",
            customer_id="CUST-002",
            status="delivered",
            items=[
                OrderItem("PROD-002", "USB-C Cable", 3, 12.99, 38.97),
            ],
            total=38.97,
            currency="USD",
            created_at=NOW - timedelta(days=20),
            updated_at=NOW - timedelta(days=15),
        ),
    }

    products: dict[str, ProductDetails] = {
        "PROD-001": ProductDetails(
            "PROD-001", "Wireless Headphones",
            "Premium noise-cancelling wireless headphones with 30-hour battery",
            79.99, "Audio", {"battery_hours": 30, "noise_cancelling": True},
            warranty_months=12,
        ),
        "PROD-002": ProductDetails(
            "PROD-002", "USB-C Cable",
            "Braided USB-C to USB-C cable, 6ft, 100W PD",
            12.99, "Accessories", {"length_ft": 6, "power_delivery_w": 100},
            warranty_months=6,
        ),
        "PROD-003": ProductDetails(
            "PROD-003", "PlayStation 5",
            "Sony PlayStation 5 console, disc edition",
            499.99, "Gaming", {"storage_gb": 825, "edition": "disc"},
            warranty_months=12,
        ),
        "PROD-004": ProductDetails(
            "PROD-004", "Laptop Stand",
            "Adjustable aluminum laptop stand, fits 10-17 inch laptops",
            45.00, "Accessories", {"material": "aluminum", "max_size_inches": 17},
            warranty_months=24,
        ),
        "PROD-005": ProductDetails(
            "PROD-005", "Mechanical Keyboard",
            "RGB mechanical keyboard with Cherry MX Blue switches",
            129.99, "Peripherals", {"switch_type": "Cherry MX Blue", "rgb": True},
            warranty_months=24,
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
            order_id="ORD-12345",
            carrier="UPS",
            tracking_number="1Z999AA10123456784",
            status="delivered",
            estimated_delivery=NOW - timedelta(days=7),
            last_location="Springfield, IL",
            events=[
                TrackingEvent(NOW - timedelta(days=12), "Chicago, IL", "Picked up", "picked_up"),
                TrackingEvent(NOW - timedelta(days=10), "Indianapolis, IN", "In transit", "in_transit"),
                TrackingEvent(NOW - timedelta(days=7), "Springfield, IL", "Delivered", "delivered"),
            ],
        ),
        "ORD-11111": ShipmentTracking(
            order_id="ORD-11111",
            carrier="FedEx",
            tracking_number="1Z999AA10123456785",
            status="in_transit",
            estimated_delivery=NOW + timedelta(days=2),
            last_location="St. Louis, MO",
            events=[
                TrackingEvent(NOW - timedelta(days=1), "Memphis, TN", "Picked up", "picked_up"),
                TrackingEvent(NOW - timedelta(hours=8), "St. Louis, MO", "In transit", "in_transit"),
            ],
        ),
        "ORD-77777": ShipmentTracking(
            order_id="ORD-77777",
            carrier="USPS",
            tracking_number="1Z999AA10123456787",
            status="in_transit",
            estimated_delivery=NOW + timedelta(days=1),
            last_location="Kansas City, MO",
            events=[
                TrackingEvent(NOW - timedelta(days=3), "Houston, TX", "Picked up", "picked_up"),
                TrackingEvent(
                    NOW - timedelta(days=1), "Kansas City, MO", "In transit", "in_transit"
                ),
            ],
        ),
    }

    returns: dict[str, ReturnStatus] = {
        "RET-001": ReturnStatus(
            return_id="RET-001",
            order_id="ORD-22222",
            status="processed",
            items=[ReturnItem("PROD-004", 1, "changed_mind")],
            created_at=NOW - timedelta(days=30),
            refund_amount=45.00,
        ),
        "RET-002": ReturnStatus(
            return_id="RET-002",
            order_id="ORD-66666",
            status="in_transit",
            items=[ReturnItem("PROD-002", 1, "defective")],
            created_at=NOW - timedelta(days=2),
        ),
    }

    # Counter for generating new IDs
    _next_order_id: int = 99000
    _next_return_id: int = 100
    _next_refund_id: int = 100
    _next_discount_id: int = 100
    _next_coupon_id: int = 100
