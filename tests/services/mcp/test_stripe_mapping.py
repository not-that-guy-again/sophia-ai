import json

from sophia.services.mcp.models import MCPToolResult
from sophia.services.mcp.stripe_mapping import (
    _parse_stripe_coupon,
    _parse_stripe_customer,
    _parse_stripe_customers,
    _parse_stripe_discount,
    _parse_stripe_refund,
)


def _wrap(data: dict) -> MCPToolResult:
    return MCPToolResult(content=[{"type": "text", "text": json.dumps(data)}])


class TestParseStripeRefund:
    def test_successful_refund(self):
        data = {
            "id": "re_1234",
            "payment_intent": "pi_abc",
            "amount": 2500,
            "currency": "usd",
            "status": "succeeded",
            "reason": "requested_by_customer",
        }
        result = _parse_stripe_refund(_wrap(data))

        assert result.refund_id == "re_1234"
        assert result.order_id == "pi_abc"
        assert result.amount == 25.0
        assert result.status == "processed"
        assert result.method == "original_payment"

    def test_failed_refund(self):
        data = {
            "id": "re_5678",
            "payment_intent": "pi_def",
            "amount": 1000,
            "status": "failed",
        }
        result = _parse_stripe_refund(_wrap(data))

        assert result.status == "failed"
        assert result.amount == 10.0


class TestParseStripeDiscount:
    def test_percent_discount(self):
        data = {
            "id": "SAVE10",
            "percent_off": 10.0,
            "amount_off": None,
            "duration": "once",
            "valid": True,
        }
        result = _parse_stripe_discount(_wrap(data))

        assert result.discount_code == "SAVE10"
        assert result.percent == 10


class TestParseStripeCoupon:
    def test_percent_coupon(self):
        data = {
            "id": "HOLIDAY20",
            "percent_off": 20.0,
            "amount_off": None,
            "currency": None,
            "duration": "once",
            "valid": True,
        }
        result = _parse_stripe_coupon(_wrap(data))

        assert result.coupon_code == "HOLIDAY20"
        assert result.type == "percent"
        assert result.value == 20.0

    def test_fixed_amount_coupon(self):
        data = {
            "id": "FLAT500",
            "percent_off": None,
            "amount_off": 500,
            "currency": "usd",
            "duration": "once",
            "valid": True,
        }
        result = _parse_stripe_coupon(_wrap(data))

        assert result.coupon_code == "FLAT500"
        assert result.type == "fixed_amount"
        assert result.value == 5.0


class TestParseStripeCustomer:
    def test_full_customer(self):
        data = {
            "id": "cus_abc123",
            "email": "alice@example.com",
            "name": "Alice Smith",
            "phone": "+14155551234",
            "created": 1700000000,
            "metadata": {},
        }
        customer = _parse_stripe_customer(_wrap(data))

        assert customer.customer_id == "cus_abc123"
        assert customer.email == "alice@example.com"
        assert customer.name == "Alice Smith"
        assert customer.phone == "+14155551234"
        assert customer.created_at is not None

    def test_customer_no_name(self):
        data = {
            "id": "cus_xyz",
            "email": "bob@test.com",
            "name": None,
            "created": 1700000000,
        }
        customer = _parse_stripe_customer(_wrap(data))

        assert customer.customer_id == "cus_xyz"
        assert customer.name == ""

    def test_customer_single_name(self):
        data = {
            "id": "cus_mono",
            "email": "mono@test.com",
            "name": "Madonna",
            "created": 1700000000,
        }
        customer = _parse_stripe_customer(_wrap(data))
        assert customer.name == "Madonna"


class TestParseStripeCustomers:
    def test_customer_list(self):
        data = {
            "data": [
                {
                    "id": "cus_1",
                    "email": "a@example.com",
                    "name": "Alice A",
                    "created": 1700000000,
                },
                {
                    "id": "cus_2",
                    "email": "b@example.com",
                    "name": "Bob B",
                    "created": 1700000000,
                },
            ]
        }
        customers = _parse_stripe_customers(_wrap(data))

        assert len(customers) == 2
        assert customers[0].customer_id == "cus_1"
        assert customers[1].customer_id == "cus_2"
