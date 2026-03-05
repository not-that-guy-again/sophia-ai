"""Mapping between Sophia service methods and Stripe MCP server tools."""

import json
from datetime import datetime

from sophia.services.mcp.exceptions import MCPParseError
from sophia.services.mcp.models import MCPToolResult
from sophia.services.models import (
    CouponResult,
    Customer,
    DiscountResult,
    RefundResult,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _extract_json(result: MCPToolResult) -> dict:
    """Extract the first text content block from an MCP result and parse as JSON."""
    if not result.content:
        raise MCPParseError("MCP result has no content blocks")
    for block in result.content:
        if block.get("type") == "text":
            try:
                return json.loads(block["text"])
            except (json.JSONDecodeError, KeyError) as exc:
                raise MCPParseError(f"Failed to parse MCP text content as JSON: {exc}") from exc
    raise MCPParseError("No text content block found in MCP result")


def _not_supported(method_name: str):
    """Create a build_args function that raises NotImplementedError."""

    def _raise(**kwargs):
        raise NotImplementedError(
            f"'{method_name}' is not supported by the Stripe MCP server. "
            f"Options: (1) implement it in a custom mapping module, "
            f"(2) use the generic REST adapter to call the Stripe API directly, "
            f"or (3) submit a feature request to the MCP server maintainer."
        )

    return _raise


# ── Parse Functions ──────────────────────────────────────────────────────────


def _parse_stripe_refund(result: MCPToolResult) -> RefundResult:
    """Parse a Stripe create_refund response into RefundResult."""
    data = _extract_json(result)
    raw_status = data.get("status", "")
    status = "processed" if raw_status == "succeeded" else "failed"
    return RefundResult(
        refund_id=str(data.get("id", "")),
        order_id=str(data.get("payment_intent", "")),
        amount=data.get("amount", 0) / 100,
        status=status,
        method="original_payment",
    )


def _parse_stripe_discount(result: MCPToolResult) -> DiscountResult:
    """Parse a Stripe create_coupon response into DiscountResult for apply_discount."""
    data = _extract_json(result)
    percent = int(data.get("percent_off") or 0)
    return DiscountResult(
        discount_code=str(data.get("id", "")),
        percent=percent,
        expiry=datetime(2099, 12, 31),
        customer_id="",
    )


def _parse_stripe_coupon(result: MCPToolResult) -> CouponResult:
    """Parse a Stripe create_coupon response into CouponResult for generate_coupon."""
    data = _extract_json(result)
    percent_off = data.get("percent_off")
    amount_off = data.get("amount_off")
    if percent_off:
        coupon_type = "percent"
        value = float(percent_off)
    elif amount_off:
        coupon_type = "fixed_amount"
        value = amount_off / 100
    else:
        coupon_type = "percent"
        value = 0.0
    return CouponResult(
        coupon_code=str(data.get("id", "")),
        type=coupon_type,
        value=value,
        expiry=datetime(2099, 12, 31),
        customer_id="",
    )


def _parse_stripe_customer(result: MCPToolResult) -> Customer:
    """Parse a Stripe retrieve_customer response into Customer."""
    data = _extract_json(result)
    name = data.get("name") or ""
    parts = name.split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""
    full_name = f"{first_name} {last_name}".strip()

    created_at = None
    if ts := data.get("created"):
        created_at = datetime.fromtimestamp(ts)

    return Customer(
        customer_id=str(data.get("id", "")),
        email=data.get("email", ""),
        name=full_name,
        phone=data.get("phone"),
        created_at=created_at,
    )


def _parse_stripe_customers(result: MCPToolResult) -> list[Customer]:
    """Parse a Stripe list_customers response into a list of Customers."""
    data = _extract_json(result)
    customers_data = data.get("data", [data]) if isinstance(data, dict) else data
    customers = []
    for cust in customers_data:
        single_result = MCPToolResult(content=[{"type": "text", "text": json.dumps(cust)}])
        customers.append(_parse_stripe_customer(single_result))
    return customers


# ── Mapping Dicts ────────────────────────────────────────────────────────────


def stripe_order_mapping() -> dict:
    """Mapping for OrderService methods — not supported by Stripe."""
    return {
        "get_order": {
            "tool_name": "get_order",
            "build_args": _not_supported("get_order"),
            "parse_response": lambda r: None,
        },
        "get_order_status": {
            "tool_name": "get_order_status",
            "build_args": _not_supported("get_order_status"),
            "parse_response": lambda r: None,
        },
        "search_orders_by_customer": {
            "tool_name": "search_orders_by_customer",
            "build_args": _not_supported("search_orders_by_customer"),
            "parse_response": lambda r: None,
        },
        "cancel_order": {
            "tool_name": "cancel_order",
            "build_args": _not_supported("cancel_order"),
            "parse_response": lambda r: None,
        },
        "update_order": {
            "tool_name": "update_order",
            "build_args": _not_supported("update_order"),
            "parse_response": lambda r: None,
        },
        "place_order": {
            "tool_name": "place_order",
            "build_args": _not_supported("place_order"),
            "parse_response": lambda r: None,
        },
    }


def stripe_customer_mapping() -> dict:
    """Mapping for CustomerService methods to Stripe MCP tools."""
    return {
        "get_customer": {
            "tool_name": "retrieve_customer",
            "build_args": lambda customer_id: {"customer_id": customer_id},
            "parse_response": _parse_stripe_customer,
        },
        "search_customers": {
            "tool_name": "list_customers",
            "build_args": lambda query: {"email": query},
            "parse_response": _parse_stripe_customers,
        },
        "get_customer_history": {
            "tool_name": "get_customer_history",
            "build_args": _not_supported("get_customer_history"),
            "parse_response": lambda r: None,
        },
    }


def stripe_shipping_mapping() -> dict:
    """Mapping for ShippingService methods — not supported by Stripe."""
    return {
        "track_shipment": {
            "tool_name": "track_shipment",
            "build_args": _not_supported("track_shipment"),
            "parse_response": lambda r: None,
        },
        "get_shipping_options": {
            "tool_name": "get_shipping_options",
            "build_args": _not_supported("get_shipping_options"),
            "parse_response": lambda r: None,
        },
        "update_shipping_address": {
            "tool_name": "update_shipping_address",
            "build_args": _not_supported("update_shipping_address"),
            "parse_response": lambda r: None,
        },
        "generate_return_label": {
            "tool_name": "generate_return_label",
            "build_args": _not_supported("generate_return_label"),
            "parse_response": lambda r: None,
        },
    }


def stripe_inventory_mapping() -> dict:
    """Mapping for InventoryService methods — not supported by Stripe."""
    return {
        "get_product_details": {
            "tool_name": "get_product_details",
            "build_args": _not_supported("get_product_details"),
            "parse_response": lambda r: None,
        },
        "check_stock": {
            "tool_name": "check_stock",
            "build_args": _not_supported("check_stock"),
            "parse_response": lambda r: None,
        },
        "check_warranty_status": {
            "tool_name": "check_warranty_status",
            "build_args": _not_supported("check_warranty_status"),
            "parse_response": lambda r: None,
        },
    }


def stripe_compensation_mapping() -> dict:
    """Mapping for CompensationService methods to Stripe MCP tools."""
    return {
        "process_full_refund": {
            "tool_name": "create_refund",
            "build_args": lambda order_id, reason: {
                "payment_intent": order_id,
                "reason": reason,
            },
            "parse_response": _parse_stripe_refund,
        },
        "process_partial_refund": {
            "tool_name": "create_refund",
            "build_args": lambda order_id, amount, reason: {
                "payment_intent": order_id,
                "amount": int(amount * 100),
                "reason": reason,
            },
            "parse_response": _parse_stripe_refund,
        },
        "apply_discount": {
            "tool_name": "create_coupon",
            "build_args": lambda customer_id, percent, reason=None: {
                "percent_off": percent,
                "duration": "once",
            },
            "parse_response": _parse_stripe_discount,
        },
        "apply_free_shipping": {
            "tool_name": "apply_free_shipping",
            "build_args": _not_supported("apply_free_shipping"),
            "parse_response": lambda r: None,
        },
        "generate_coupon": {
            "tool_name": "create_coupon",
            "build_args": lambda params: {
                "percent_off": params.value if params.type == "percent" else None,
                "amount_off": int(params.value * 100) if params.type == "fixed_amount" else None,
                "currency": "usd" if params.type == "fixed_amount" else None,
                "duration": "once",
            },
            "parse_response": _parse_stripe_coupon,
        },
        "initiate_return": {
            "tool_name": "initiate_return",
            "build_args": _not_supported("initiate_return"),
            "parse_response": lambda r: None,
        },
        "check_return_status": {
            "tool_name": "check_return_status",
            "build_args": _not_supported("check_return_status"),
            "parse_response": lambda r: None,
        },
    }
