from abc import ABC, abstractmethod

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


class CompensationService(ABC):
    @abstractmethod
    async def apply_discount(
        self, customer_id: str, percent: int, reason: str
    ) -> DiscountResult: ...

    @abstractmethod
    async def process_partial_refund(
        self, order_id: str, amount: float, reason: str
    ) -> RefundResult: ...

    @abstractmethod
    async def process_full_refund(
        self, order_id: str, reason: str
    ) -> RefundResult: ...

    @abstractmethod
    async def apply_free_shipping(
        self, customer_id: str, order_id: str | None, reason: str
    ) -> FreeShippingResult: ...

    @abstractmethod
    async def generate_coupon(
        self, customer_id: str, params: CouponParams
    ) -> CouponResult: ...

    @abstractmethod
    async def initiate_return(
        self, order_id: str, items: list[ReturnItem], reason: str
    ) -> ReturnInitiationResult: ...

    @abstractmethod
    async def check_return_status(self, return_id: str) -> ReturnStatus | None: ...
