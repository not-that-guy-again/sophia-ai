"""Mapping between Sophia service methods and WooCommerce MCP server tools."""

import json
from datetime import datetime

from sophia.services.mcp.exceptions import MCPParseError
from sophia.services.mcp.models import MCPToolResult
from sophia.services.models import (
    Address,
    CancellationResult,
    Customer,
    CustomerHistory,
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


_WC_STATUS_MAP: dict[str, str] = {
    "pending": "pending",
    "processing": "processing",
    "on-hold": "pending",
    "completed": "delivered",
    "cancelled": "cancelled",
    "refunded": "cancelled",
    "failed": "cancelled",
    "checkout-draft": "pending",
}


def _map_wc_status(status: str | None) -> str:
    """Map WooCommerce order status to Sophia's status values."""
    return _WC_STATUS_MAP.get(status or "", "pending")


def _extract_wc_tracking(meta_data: list) -> str | None:
    """Extract tracking number from WooCommerce order meta_data."""
    for item in meta_data or []:
        if item.get("key") == "_tracking_number":
            return item.get("value")
    return None


def _not_supported(method_name: str):
    """Create a build_args function that raises NotImplementedError."""

    def _raise(**kwargs):
        raise NotImplementedError(
            f"'{method_name}' is not supported by the WooCommerce MCP server. "
            f"Options: (1) implement it in a custom mapping module, "
            f"(2) use the generic REST adapter to call the WooCommerce API directly, "
            f"or (3) submit a feature request to the MCP server maintainer."
        )

    return _raise


# ── Parse Functions ──────────────────────────────────────────────────────────


def _parse_wc_order(result: MCPToolResult) -> Order:
    """Parse a WooCommerce order response into Sophia's Order dataclass."""
    data = _extract_json(result)

    items = []
    for li in data.get("line_items", []):
        items.append(
            OrderItem(
                product_id=str(li.get("product_id", "")),
                name=li.get("name", ""),
                quantity=li.get("quantity", 1),
                unit_price=float(li.get("price", 0)),
                total_price=float(li.get("total", 0)),
            )
        )

    shipping_address = None
    if addr := data.get("shipping"):
        shipping_address = Address(
            line1=addr.get("address_1", ""),
            line2=addr.get("address_2") or None,
            city=addr.get("city", ""),
            state=addr.get("state", ""),
            postal_code=addr.get("postcode", ""),
            country=addr.get("country", "US"),
        )

    return Order(
        order_id=str(data.get("id", "")),
        customer_id=str(data.get("customer_id", "")),
        status=_map_wc_status(data.get("status")),
        items=items,
        total=float(data.get("total", 0)),
        currency=data.get("currency", "USD"),
        created_at=_parse_datetime(data.get("date_created")),
        updated_at=_parse_datetime(data.get("date_modified")),
        shipping_address=shipping_address,
        tracking_number=_extract_wc_tracking(data.get("meta_data", [])),
    )


def _parse_wc_orders(result: MCPToolResult) -> list[Order]:
    """Parse a WooCommerce list_orders response into a list of Orders."""
    data = _extract_json(result)
    orders_data = data.get("orders", [data]) if isinstance(data, dict) else data
    orders = []
    for order_data in orders_data:
        single_result = MCPToolResult(
            content=[{"type": "text", "text": json.dumps(order_data)}]
        )
        orders.append(_parse_wc_order(single_result))
    return orders


def _parse_wc_order_status(result: MCPToolResult) -> OrderStatus:
    """Parse a WooCommerce order response into OrderStatus."""
    data = _extract_json(result)
    return OrderStatus(
        order_id=str(data.get("id", "")),
        status=_map_wc_status(data.get("status")),
        last_updated=_parse_datetime(data.get("date_modified")),
        tracking_number=_extract_wc_tracking(data.get("meta_data", [])),
    )


def _parse_wc_cancellation(result: MCPToolResult) -> CancellationResult:
    """Parse a WooCommerce cancel_order response."""
    data = _extract_json(result)
    return CancellationResult(
        order_id=str(data.get("id", "")),
        success=data.get("status") == "cancelled",
        refund_amount=float(data.get("total", 0)),
    )


def _parse_wc_customer(result: MCPToolResult) -> Customer:
    """Parse a WooCommerce customer response into Sophia's Customer dataclass."""
    data = _extract_json(result)
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip()
    return Customer(
        customer_id=str(data.get("id", "")),
        email=data.get("email", ""),
        name=full_name,
        created_at=_parse_datetime(data.get("date_created")),
        total_orders=data.get("orders_count", 0),
        total_spent=float(data.get("total_spent", 0)),
    )


def _parse_wc_customers(result: MCPToolResult) -> list[Customer]:
    """Parse a WooCommerce list_customers response."""
    data = _extract_json(result)
    customers_data = (
        data.get("customers", [data]) if isinstance(data, dict) else data
    )
    customers = []
    for cust in customers_data:
        single_result = MCPToolResult(
            content=[{"type": "text", "text": json.dumps(cust)}]
        )
        customers.append(_parse_wc_customer(single_result))
    return customers


def _parse_wc_customer_history(result: MCPToolResult) -> CustomerHistory:
    """Parse a WooCommerce orders list as customer history."""
    data = _extract_json(result)
    orders_data = data.get("orders", [data]) if isinstance(data, dict) else data
    orders = []
    for order_data in orders_data:
        single_result = MCPToolResult(
            content=[{"type": "text", "text": json.dumps(order_data)}]
        )
        orders.append(_parse_wc_order(single_result))

    customer = Customer(
        customer_id=str(orders_data[0].get("customer_id", "")) if orders_data else "",
        email="",
        name="",
    )
    return CustomerHistory(
        customer=customer,
        orders=orders,
        returns=[],
    )


def _parse_wc_product(result: MCPToolResult) -> ProductDetails:
    """Parse a WooCommerce product response into ProductDetails."""
    data = _extract_json(result)
    categories = data.get("categories", [])
    category = categories[0].get("name", "") if categories else ""
    return ProductDetails(
        product_id=str(data.get("id", "")),
        name=data.get("name", ""),
        description=data.get("description", ""),
        price=float(data.get("price", 0)),
        category=category,
    )


def _parse_wc_stock(result: MCPToolResult) -> list[ProductStock]:
    """Parse a WooCommerce products list for stock information."""
    data = _extract_json(result)
    products_data = (
        data.get("products", [data]) if isinstance(data, dict) else data
    )
    stocks = []
    for prod in products_data:
        qty = prod.get("stock_quantity") or 0
        in_stock = prod.get("stock_status", "") == "instock"
        stocks.append(
            ProductStock(
                product_id=str(prod.get("id", "")),
                name=prod.get("name", ""),
                quantity_available=qty,
                price=float(prod.get("price", 0)),
                in_stock=in_stock,
            )
        )
    return stocks


def _parse_wc_refund(result: MCPToolResult) -> RefundResult:
    """Parse a WooCommerce refund response into RefundResult."""
    data = _extract_json(result)
    return RefundResult(
        refund_id=str(data.get("id", "")),
        order_id=str(data.get("order_id", "")),
        amount=abs(float(data.get("amount", 0))),
        status="processed" if data.get("id") else "failed",
        method="original_payment",
    )


# ── Mapping Dicts ────────────────────────────────────────────────────────────


def woocommerce_order_mapping() -> dict:
    """Mapping for OrderService methods to WooCommerce MCP tools."""
    return {
        "get_order": {
            "tool_name": "wc_orders_get",
            "build_args": lambda order_id: {"order_id": order_id},
            "parse_response": _parse_wc_order,
        },
        "get_order_status": {
            "tool_name": "wc_orders_get",
            "build_args": lambda order_id: {"order_id": order_id},
            "parse_response": _parse_wc_order_status,
        },
        "search_orders_by_customer": {
            "tool_name": "wc_orders_list",
            "build_args": lambda customer_id, limit=20: {
                "customer": customer_id,
                "per_page": limit,
            },
            "parse_response": _parse_wc_orders,
        },
        "cancel_order": {
            "tool_name": "wc_orders_update",
            "build_args": lambda order_id, reason: {
                "order_id": order_id,
                "status": "cancelled",
            },
            "parse_response": _parse_wc_cancellation,
        },
        "update_order": {
            "tool_name": "wc_orders_update",
            "build_args": _not_supported("update_order"),
            "parse_response": lambda r: None,
        },
        "place_order": {
            "tool_name": "place_order",
            "build_args": _not_supported("place_order"),
            "parse_response": lambda r: None,
        },
    }


def woocommerce_customer_mapping() -> dict:
    """Mapping for CustomerService methods to WooCommerce MCP tools."""
    return {
        "get_customer": {
            "tool_name": "wc_customers_get",
            "build_args": lambda customer_id: {"customer_id": customer_id},
            "parse_response": _parse_wc_customer,
        },
        "search_customers": {
            "tool_name": "wc_customers_list",
            "build_args": lambda query: {"search": query},
            "parse_response": _parse_wc_customers,
        },
        "get_customer_history": {
            "tool_name": "wc_orders_list",
            "build_args": lambda customer_id: {"customer": customer_id},
            "parse_response": _parse_wc_customer_history,
        },
    }


def woocommerce_shipping_mapping() -> dict:
    """Mapping for ShippingService methods — WooCommerce has no native shipping tracking."""
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


def woocommerce_inventory_mapping() -> dict:
    """Mapping for InventoryService methods to WooCommerce MCP tools."""
    return {
        "get_product_details": {
            "tool_name": "wc_products_get",
            "build_args": lambda product_id: {"product_id": product_id},
            "parse_response": _parse_wc_product,
        },
        "check_stock": {
            "tool_name": "wc_products_list",
            "build_args": lambda product_id=None: {"product_id": product_id}
            if product_id
            else {},
            "parse_response": _parse_wc_stock,
        },
        "check_warranty_status": {
            "tool_name": "check_warranty_status",
            "build_args": _not_supported("check_warranty_status"),
            "parse_response": lambda r: None,
        },
    }


def woocommerce_compensation_mapping() -> dict:
    """Mapping for CompensationService methods to WooCommerce MCP tools."""
    return {
        "process_full_refund": {
            "tool_name": "wc_refunds_create",
            "build_args": lambda order_id, reason: {
                "order_id": order_id,
                "reason": reason,
            },
            "parse_response": _parse_wc_refund,
        },
        "process_partial_refund": {
            "tool_name": "wc_refunds_create",
            "build_args": lambda order_id, amount, reason: {
                "order_id": order_id,
                "amount": str(amount),
                "reason": reason,
            },
            "parse_response": _parse_wc_refund,
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
