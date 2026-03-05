import uuid
from datetime import datetime, timedelta

from sophia.services.compensation import CompensationService
from sophia.services.models import (
    CouponParams,
    CouponResult,
    DiscountResult,
    FreeShippingResult,
    RefundResult,
    ReturnInitiationResult,
    ReturnItem,
    ReturnStatus,
)

from .mock_data import MockDataStore


class MockCompensationService(CompensationService):
    async def apply_discount(self, customer_id: str, percent: int, reason: str) -> DiscountResult:
        customer = MockDataStore.customers.get(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        MockDataStore._next_discount_id += 1
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

        MockDataStore._next_refund_id += 1
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

        MockDataStore._next_refund_id += 1
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

        return FreeShippingResult(
            applied=True,
            customer_id=customer_id,
            estimated_savings=9.99,
        )

    async def generate_coupon(self, customer_id: str, params: CouponParams) -> CouponResult:
        customer = MockDataStore.customers.get(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        MockDataStore._next_coupon_id += 1
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

        # Check 30-day window
        days_since_delivery = (datetime.now() - order.updated_at).days
        if days_since_delivery > 30:
            raise ValueError("Return window (30 days from delivery) has expired")

        # Check for existing active return
        existing = [
            r
            for r in MockDataStore.returns.values()
            if r.order_id == order_id and r.status not in ("processed", "cancelled")
        ]
        if existing:
            raise ValueError(f"Order {order_id} already has an active return")

        MockDataStore._next_return_id += 1
        return_id = f"RET-{MockDataStore._next_return_id:03d}"

        # Determine if free return shipping
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
            else ("Ship items back at your expense. Include the return ID on the package.")
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
