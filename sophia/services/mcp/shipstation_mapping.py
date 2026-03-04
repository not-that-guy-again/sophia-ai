"""Mapping between Sophia service methods and ShipStation MCP server tools."""

import json
from datetime import datetime, timedelta

from sophia.services.mcp.exceptions import MCPParseError
from sophia.services.mcp.models import MCPToolResult
from sophia.services.models import (
    AddressUpdateResult,
    ReturnLabel,
    ShipmentTracking,
    ShippingOption,
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


def _not_supported(method_name: str):
    """Create a build_args function that raises NotImplementedError."""

    def _raise(**kwargs):
        raise NotImplementedError(
            f"'{method_name}' is not supported by the ShipStation MCP server. "
            f"Options: (1) implement it in a custom mapping module, "
            f"(2) use the generic REST adapter to call the ShipStation API directly, "
            f"or (3) submit a feature request to the MCP server maintainer."
        )

    return _raise


# ── Parse Functions ──────────────────────────────────────────────────────────


def _parse_shipstation_tracking(result: MCPToolResult) -> ShipmentTracking:
    """Parse a ShipStation get_shipment response into ShipmentTracking."""
    data = _extract_json(result)
    return ShipmentTracking(
        order_id=str(data.get("order_id", "")),
        carrier=data.get("carrier_code", ""),
        tracking_number=data.get("tracking_number", ""),
        status=data.get("status", "pending"),
        estimated_delivery=_parse_datetime(data.get("ship_date")),
    )


def _parse_shipstation_carrier_services(
    result: MCPToolResult,
) -> list[ShippingOption]:
    """Parse a ShipStation list_carrier_services response into ShippingOptions."""
    data = _extract_json(result)
    options = []
    for svc in data.get("services", []):
        options.append(
            ShippingOption(
                carrier=svc.get("carrier_code", ""),
                service=svc.get("name", ""),
                estimated_days=0,
                cost=0.0,
            )
        )
    return options


def _parse_shipstation_address_update(
    result: MCPToolResult,
) -> AddressUpdateResult:
    """Parse a ShipStation update_order response for address update."""
    data = _extract_json(result)
    return AddressUpdateResult(
        order_id=str(data.get("order_id", data.get("id", ""))),
        success=True,
    )


def _parse_shipstation_return_label(result: MCPToolResult) -> ReturnLabel:
    """Parse a ShipStation create_label response into ReturnLabel."""
    data = _extract_json(result)
    label_download = data.get("label_download", {})
    return ReturnLabel(
        label_url=label_download.get("pdf", ""),
        tracking_number=data.get("tracking_number", ""),
        carrier=data.get("carrier_code", ""),
        expiry=datetime.now() + timedelta(days=30),
    )


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO datetime string, returning None if absent."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# ── Mapping Dicts ────────────────────────────────────────────────────────────


def shipstation_order_mapping() -> dict:
    """Mapping for OrderService methods — not supported by ShipStation."""
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


def shipstation_customer_mapping() -> dict:
    """Mapping for CustomerService methods — not supported by ShipStation."""
    return {
        "get_customer": {
            "tool_name": "get_customer",
            "build_args": _not_supported("get_customer"),
            "parse_response": lambda r: None,
        },
        "search_customers": {
            "tool_name": "search_customers",
            "build_args": _not_supported("search_customers"),
            "parse_response": lambda r: None,
        },
        "get_customer_history": {
            "tool_name": "get_customer_history",
            "build_args": _not_supported("get_customer_history"),
            "parse_response": lambda r: None,
        },
    }


def shipstation_shipping_mapping() -> dict:
    """Mapping for ShippingService methods to ShipStation MCP tools."""
    return {
        "track_shipment": {
            "tool_name": "get_shipment",
            "build_args": lambda order_id: {"order_id": order_id},
            "parse_response": _parse_shipstation_tracking,
        },
        "get_shipping_options": {
            "tool_name": "list_carrier_services",
            "build_args": lambda **kwargs: {},
            "parse_response": _parse_shipstation_carrier_services,
        },
        "update_shipping_address": {
            "tool_name": "update_order",
            "build_args": lambda order_id, address: {
                "order_id": order_id,
                "ship_to": address,
            },
            "parse_response": _parse_shipstation_address_update,
        },
        "generate_return_label": {
            "tool_name": "create_label",
            "build_args": lambda order_id, reason: {
                "order_id": order_id,
                "is_return_label": True,
                "label_layout": "4x6",
            },
            "parse_response": _parse_shipstation_return_label,
        },
    }


def shipstation_inventory_mapping() -> dict:
    """Mapping for InventoryService methods — not supported by ShipStation."""
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


def shipstation_compensation_mapping() -> dict:
    """Mapping for CompensationService methods — not supported by ShipStation."""
    return {
        "process_full_refund": {
            "tool_name": "process_full_refund",
            "build_args": _not_supported("process_full_refund"),
            "parse_response": lambda r: None,
        },
        "process_partial_refund": {
            "tool_name": "process_partial_refund",
            "build_args": _not_supported("process_partial_refund"),
            "parse_response": lambda r: None,
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
