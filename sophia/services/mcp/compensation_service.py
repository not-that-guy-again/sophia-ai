from sophia.services.compensation import CompensationService
from sophia.services.mcp.adapter import MCPServiceAdapter
from sophia.services.mcp.client import MCPClient
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


class MCPCompensationService(CompensationService):
    def __init__(self, client: MCPClient, tool_mapping: dict):
        self.adapter = MCPServiceAdapter(client, tool_mapping)

    async def apply_discount(
        self, customer_id: str, percent: int, reason: str
    ) -> DiscountResult:
        return await self.adapter._call(
            "apply_discount", customer_id=customer_id, percent=percent, reason=reason
        )

    async def process_partial_refund(
        self, order_id: str, amount: float, reason: str
    ) -> RefundResult:
        return await self.adapter._call(
            "process_partial_refund", order_id=order_id, amount=amount, reason=reason
        )

    async def process_full_refund(
        self, order_id: str, reason: str
    ) -> RefundResult:
        return await self.adapter._call(
            "process_full_refund", order_id=order_id, reason=reason
        )

    async def apply_free_shipping(
        self, customer_id: str, order_id: str | None, reason: str
    ) -> FreeShippingResult:
        return await self.adapter._call(
            "apply_free_shipping",
            customer_id=customer_id,
            order_id=order_id,
            reason=reason,
        )

    async def generate_coupon(
        self, customer_id: str, params: CouponParams
    ) -> CouponResult:
        return await self.adapter._call(
            "generate_coupon", customer_id=customer_id, params=params
        )

    async def initiate_return(
        self, order_id: str, items: list[ReturnItem], reason: str
    ) -> ReturnInitiationResult:
        return await self.adapter._call(
            "initiate_return", order_id=order_id, items=items, reason=reason
        )

    async def check_return_status(self, return_id: str) -> ReturnStatus | None:
        return await self.adapter._call("check_return_status", return_id=return_id)
