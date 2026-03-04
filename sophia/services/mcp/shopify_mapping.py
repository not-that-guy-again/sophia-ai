"""Mapping between Sophia service methods and Shopify MCP server tools."""

import json
from datetime import datetime

from sophia.services.mcp.exceptions import MCPParseError
from sophia.services.mcp.models import MCPToolResult
from sophia.services.models import (
    Address,
    CancellationResult,
    Customer,
    Order,
    OrderItem,
    OrderStatus,
    ProductDetails,
    ProductStock,
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
                raise MCPParseError(
                    f"Failed to parse MCP text content as JSON: {exc}"
                ) from exc
    raise MCPParseError("No text content block found in MCP result")


def _parse_datetime(value: str | None) -> datetime:
    """Parse an ISO datetime string, returning epoch if None."""
    if not value:
        return datetime(1970, 1, 1)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime(1970, 1, 1)


def _map_shopify_status(fulfillment_status: str | None) -> str:
    """Map Shopify fulfillment statuses to Sophia's order status values."""
    mapping = {
        None: "pending",
        "": "pending",
        "unfulfilled": "pending",
        "partial": "confirmed",
        "fulfilled": "shipped",
        "restocked": "cancelled",
    }
    return mapping.get(fulfillment_status, "pending")


def _map_shopify_financial_status(financial_status: str | None) -> str:
    """Map Shopify financial status for cancellation/refund context."""
    mapping = {
        "refunded": "cancelled",
        "voided": "cancelled",
        "paid": "confirmed",
        "pending": "pending",
    }
    return mapping.get(financial_status or "", "pending")


# ── Parse Functions ──────────────────────────────────────────────────────────


def _parse_shopify_order(result: MCPToolResult) -> Order:
    """Parse a Shopify order response into Sophia's Order dataclass."""
    data = _extract_json(result)

    items = []
    for li in data.get("line_items", []):
        items.append(
            OrderItem(
                product_id=str(li.get("product_id", "")),
                name=li.get("title", li.get("name", "")),
                quantity=li.get("quantity", 1),
                unit_price=float(li.get("price", 0)),
                total_price=float(li.get("price", 0)) * li.get("quantity", 1),
            )
        )

    shipping_address = None
    if addr := data.get("shipping_address"):
        shipping_address = Address(
            line1=addr.get("address1", ""),
            line2=addr.get("address2"),
            city=addr.get("city", ""),
            state=addr.get("province", ""),
            postal_code=addr.get("zip", ""),
            country=addr.get("country_code", "US"),
        )

    status = _map_shopify_status(data.get("fulfillment_status"))
    if data.get("cancelled_at"):
        status = "cancelled"

    return Order(
        order_id=str(data.get("id", "")),
        customer_id=str(data.get("customer", {}).get("id", "")),
        status=status,
        items=items,
        total=float(data.get("total_price", 0)),
        currency=data.get("currency", "USD"),
        created_at=_parse_datetime(data.get("created_at")),
        updated_at=_parse_datetime(data.get("updated_at")),
        shipping_address=shipping_address,
        tracking_number=data.get("fulfillments", [{}])[0].get("tracking_number")
        if data.get("fulfillments")
        else None,
    )


def _parse_shopify_orders(result: MCPToolResult) -> list[Order]:
    """Parse a Shopify list_orders response into a list of Order dataclasses."""
    data = _extract_json(result)
    orders_data = data.get("orders", [data]) if isinstance(data, dict) else data
    orders = []
    for order_data in orders_data:
        # Re-wrap each order for parse_shopify_order
        single_result = MCPToolResult(
            content=[{"type": "text", "text": json.dumps(order_data)}]
        )
        orders.append(_parse_shopify_order(single_result))
    return orders


def _parse_shopify_order_status(result: MCPToolResult) -> OrderStatus:
    """Parse a Shopify order into an OrderStatus."""
    data = _extract_json(result)
    status = _map_shopify_status(data.get("fulfillment_status"))
    if data.get("cancelled_at"):
        status = "cancelled"

    tracking = None
    if fulfillments := data.get("fulfillments"):
        tracking = fulfillments[0].get("tracking_number")

    return OrderStatus(
        order_id=str(data.get("id", "")),
        status=status,
        last_updated=_parse_datetime(data.get("updated_at")),
        tracking_number=tracking,
    )


def _parse_shopify_cancellation(result: MCPToolResult) -> CancellationResult:
    """Parse a Shopify cancel_order response."""
    data = _extract_json(result)
    return CancellationResult(
        order_id=str(data.get("id", "")),
        success=data.get("cancelled_at") is not None,
        refund_amount=float(data.get("total_price", 0)),
    )


def _parse_shopify_customer(result: MCPToolResult) -> Customer:
    """Parse a Shopify customer response into Sophia's Customer dataclass."""
    data = _extract_json(result)
    return Customer(
        customer_id=str(data.get("id", "")),
        email=data.get("email", ""),
        name=f"{data.get('first_name', '')} {data.get('last_name', '')}".strip(),
        phone=data.get("phone"),
        created_at=_parse_datetime(data.get("created_at")),
        total_orders=data.get("orders_count", 0),
        total_spent=float(data.get("total_spent", 0)),
        tags=[t.strip() for t in data.get("tags", "").split(",") if t.strip()]
        if isinstance(data.get("tags"), str)
        else data.get("tags", []),
    )


def _parse_shopify_customers(result: MCPToolResult) -> list[Customer]:
    """Parse a Shopify search_customers response."""
    data = _extract_json(result)
    customers_data = (
        data.get("customers", [data]) if isinstance(data, dict) else data
    )
    customers = []
    for cust in customers_data:
        single_result = MCPToolResult(
            content=[{"type": "text", "text": json.dumps(cust)}]
        )
        customers.append(_parse_shopify_customer(single_result))
    return customers


def _parse_shopify_product(result: MCPToolResult) -> ProductDetails:
    """Parse a Shopify product response."""
    data = _extract_json(result)
    variants = data.get("variants", [{}])
    price = float(variants[0].get("price", 0)) if variants else 0

    return ProductDetails(
        product_id=str(data.get("id", "")),
        name=data.get("title", ""),
        description=data.get("body_html", ""),
        price=price,
        category=data.get("product_type", ""),
    )


def _parse_shopify_inventory(result: MCPToolResult) -> list[ProductStock]:
    """Parse a Shopify inventory level response."""
    data = _extract_json(result)
    levels = data.get("inventory_levels", [data]) if isinstance(data, dict) else data
    stocks = []
    for level in levels:
        qty = level.get("available", 0)
        stocks.append(
            ProductStock(
                product_id=str(level.get("inventory_item_id", "")),
                name="",
                quantity_available=qty,
                price=0.0,
                in_stock=qty > 0,
            )
        )
    return stocks


def _parse_shopify_refund(result: MCPToolResult) -> RefundResult:
    """Parse a Shopify refund response."""
    data = _extract_json(result)
    transactions = data.get("transactions", [])
    amount = 0.0
    if transactions:
        amount = float(transactions[0].get("amount", 0))

    return RefundResult(
        refund_id=str(data.get("id", "")),
        order_id=str(data.get("order_id", "")),
        amount=amount,
        status="processed" if data.get("id") else "failed",
        method="original_payment",
    )


def _not_supported(method_name: str):
    """Create a build_args function that raises NotImplementedError."""

    def _raise(**kwargs):
        raise NotImplementedError(
            f"'{method_name}' is not supported by the Shopify MCP server. "
            f"Options: (1) implement it in a custom mapping module, "
            f"(2) use the generic REST adapter to call the Shopify Admin API directly, "
            f"or (3) submit a feature request to the MCP server maintainer."
        )

    return _raise


# ── Mapping Dicts ────────────────────────────────────────────────────────────


def shopify_order_mapping() -> dict:
    """Mapping for OrderService methods to Shopify MCP tools."""
    return {
        "get_order": {
            "tool_name": "get_order",
            "build_args": lambda order_id: {"order_id": order_id},
            "parse_response": _parse_shopify_order,
        },
        "get_order_status": {
            "tool_name": "get_order",
            "build_args": lambda order_id: {"order_id": order_id},
            "parse_response": _parse_shopify_order_status,
        },
        "search_orders_by_customer": {
            "tool_name": "list_orders",
            "build_args": lambda customer_id, limit=20: {
                "customer_id": customer_id,
                "limit": limit,
            },
            "parse_response": _parse_shopify_orders,
        },
        "cancel_order": {
            "tool_name": "cancel_order",
            "build_args": lambda order_id, reason: {
                "order_id": order_id,
                "reason": reason,
            },
            "parse_response": _parse_shopify_cancellation,
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


def shopify_customer_mapping() -> dict:
    """Mapping for CustomerService methods to Shopify MCP tools."""
    return {
        "get_customer": {
            "tool_name": "get_customer",
            "build_args": lambda customer_id: {"customer_id": customer_id},
            "parse_response": _parse_shopify_customer,
        },
        "search_customers": {
            "tool_name": "search_customers",
            "build_args": lambda query: {"query": query},
            "parse_response": _parse_shopify_customers,
        },
        "get_customer_history": {
            "tool_name": "get_customer_history",
            "build_args": _not_supported("get_customer_history"),
            "parse_response": lambda r: None,
        },
    }


def shopify_inventory_mapping() -> dict:
    """Mapping for InventoryService methods to Shopify MCP tools."""
    return {
        "get_product_details": {
            "tool_name": "get_product",
            "build_args": lambda product_id: {"product_id": product_id},
            "parse_response": _parse_shopify_product,
        },
        "check_stock": {
            "tool_name": "get_inventory_level",
            "build_args": lambda product_id=None: {"product_id": product_id}
            if product_id
            else {},
            "parse_response": _parse_shopify_inventory,
        },
        "check_warranty_status": {
            "tool_name": "check_warranty_status",
            "build_args": _not_supported("warranty checks"),
            "parse_response": lambda r: None,
        },
    }


def shopify_compensation_mapping() -> dict:
    """Mapping for CompensationService methods to Shopify MCP tools."""
    return {
        "process_full_refund": {
            "tool_name": "create_refund",
            "build_args": lambda order_id, reason: {
                "order_id": order_id,
                "reason": reason,
            },
            "parse_response": _parse_shopify_refund,
        },
        "process_partial_refund": {
            "tool_name": "create_refund",
            "build_args": lambda order_id, amount, reason: {
                "order_id": order_id,
                "amount": amount,
                "reason": reason,
            },
            "parse_response": _parse_shopify_refund,
        },
        "apply_discount": {
            "tool_name": "apply_discount",
            "build_args": _not_supported("apply_discount"),
            "parse_response": lambda r: None,
        },
        "apply_free_shipping": {
            "tool_name": "apply_free_shipping",
            "build_args": _not_supported("apply_free_shipping"),
            "parse_response": lambda r: None,
        },
        "generate_coupon": {
            "tool_name": "generate_coupon",
            "build_args": _not_supported("generate_coupon"),
            "parse_response": lambda r: None,
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
