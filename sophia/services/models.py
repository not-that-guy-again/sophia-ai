from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Address:
    line1: str
    city: str
    state: str
    postal_code: str
    line2: str | None = None
    country: str = "US"


@dataclass
class OrderItem:
    product_id: str
    name: str
    quantity: int
    unit_price: float
    total_price: float


@dataclass
class OrderChanges:
    shipping_address: Address | None = None
    items_to_add: list[OrderItem] | None = None
    items_to_remove: list[str] | None = None  # product IDs


@dataclass
class Order:
    order_id: str
    customer_id: str
    status: str  # "pending", "confirmed", "shipped", "delivered", "cancelled"
    items: list[OrderItem]
    total: float
    currency: str
    created_at: datetime
    updated_at: datetime
    shipping_address: Address | None = None
    tracking_number: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class OrderStatus:
    order_id: str
    status: str
    last_updated: datetime
    estimated_delivery: datetime | None = None
    tracking_number: str | None = None


@dataclass
class Customer:
    customer_id: str
    email: str
    name: str
    phone: str | None = None
    created_at: datetime | None = None
    total_orders: int = 0
    total_spent: float = 0.0
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class TrackingEvent:
    timestamp: datetime
    location: str
    description: str
    status: str


@dataclass
class ShipmentTracking:
    order_id: str
    carrier: str
    tracking_number: str
    status: str  # "label_created", "in_transit", "out_for_delivery", "delivered", "exception"
    estimated_delivery: datetime | None
    last_location: str | None = None
    events: list[TrackingEvent] = field(default_factory=list)


@dataclass
class ProductStock:
    product_id: str
    name: str
    quantity_available: int
    price: float
    in_stock: bool = True


@dataclass
class ProductDetails:
    product_id: str
    name: str
    description: str
    price: float
    category: str
    specs: dict = field(default_factory=dict)
    warranty_months: int = 12


@dataclass
class WarrantyStatus:
    order_id: str
    product_id: str
    purchase_date: datetime
    warranty_expiry: datetime
    is_active: bool
    coverage_type: str  # "standard", "extended", "none"


@dataclass
class RefundResult:
    refund_id: str
    order_id: str
    amount: float
    status: str  # "processed", "pending", "failed"
    method: str  # "original_payment", "store_credit"


@dataclass
class DiscountResult:
    discount_code: str
    percent: int
    expiry: datetime
    customer_id: str


@dataclass
class CouponParams:
    type: str  # "percent", "fixed_amount", "free_shipping"
    value: float
    min_order_amount: float | None = None
    expiry_days: int = 30
    single_use: bool = True


@dataclass
class CouponResult:
    coupon_code: str
    type: str
    value: float
    expiry: datetime
    customer_id: str


@dataclass
class ReturnItem:
    product_id: str
    quantity: int
    reason: str  # "defective", "wrong_item", "not_as_described", "changed_mind"


@dataclass
class ReturnInitiationResult:
    return_id: str
    order_id: str
    return_label_url: str | None
    status: str
    instructions: str


@dataclass
class ReturnStatus:
    return_id: str
    order_id: str
    status: str  # "initiated", "label_sent", "in_transit", "received", "processed"
    items: list[ReturnItem]
    created_at: datetime
    refund_amount: float | None = None


@dataclass
class CustomerHistory:
    customer: Customer
    orders: list[Order]
    returns: list[ReturnStatus]
    total_refunded: float = 0.0
    total_discounts_given: int = 0


@dataclass
class ReturnLabel:
    label_url: str
    carrier: str
    tracking_number: str
    expiry: datetime


@dataclass
class CancellationResult:
    order_id: str
    success: bool
    reason: str | None = None
    refund_amount: float | None = None


@dataclass
class AddressUpdateResult:
    order_id: str
    success: bool
    new_address: Address | None = None
    failure_reason: str | None = None


@dataclass
class ShippingOption:
    carrier: str
    service: str
    estimated_days: int
    cost: float


@dataclass
class FreeShippingResult:
    applied: bool
    customer_id: str
    estimated_savings: float
