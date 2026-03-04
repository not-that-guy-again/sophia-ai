# Contributing a Platform Mapping

This guide walks you through creating an MCP platform mapping module for Sophia. A platform mapping connects Sophia's service interfaces to a specific platform's MCP server, translating between Sophia's internal data models and the platform's API responses.

By the end of this guide you will have a working mapping module that lets Sophia use your platform as a backend for any of its five service types: orders, customers, shipping, inventory, and compensation.

## Prerequisites

- A working Sophia installation (`uv sync`)
- Familiarity with the target platform's API and data model
- Access to a running MCP server for the target platform (or its API docs)
- Python 3.11+

## How Platform Mappings Work

Sophia's MCP integration has three layers:

1. **`MCPClient`** — handles JSON-RPC transport, retries, and authentication
2. **`MCPServiceAdapter`** — dispatches service method calls through a mapping dict
3. **Platform mapping module** — provides the mapping dict that translates between Sophia's service methods and the platform's MCP tools

You are writing layer 3. The other two layers are framework code you don't touch.

Each mapping dict entry tells the adapter:
- Which MCP tool to call (`tool_name`)
- How to build arguments from Sophia's method parameters (`build_args`)
- How to parse the MCP response into Sophia's data models (`parse_response`)

```python
{
    "get_order": {
        "tool_name": "get_order",          # MCP tool name on the server
        "build_args": lambda order_id: {"order_id": order_id},
        "parse_response": _parse_order,     # MCPToolResult -> Order
    },
}
```

## Step 1: Create the Mapping Module

Create a new file at `sophia/services/mcp/<platform>_mapping.py`. The file must export one mapping function per service type, named `<platform>_<service>_mapping`.

For a platform called `acme`, you need:

```
sophia/services/mcp/acme_mapping.py
```

Exporting:
- `acme_order_mapping() -> dict`
- `acme_customer_mapping() -> dict`
- `acme_shipping_mapping() -> dict`
- `acme_inventory_mapping() -> dict`
- `acme_compensation_mapping() -> dict`

### Reference: Shopify mapping module

The Shopify mapping at `sophia/services/mcp/shopify_mapping.py` is the canonical example. Study it before writing your own.

## Step 2: Write the Helpers

Every mapping module needs a few helper functions.

### Extract JSON from MCP responses

MCP tools return content blocks. You need to extract the JSON payload:

```python
import json
from sophia.services.mcp.exceptions import MCPParseError
from sophia.services.mcp.models import MCPToolResult


def _extract_json(result: MCPToolResult) -> dict:
    """Extract the first text content block and parse as JSON."""
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
```

This helper is identical across platforms. You can copy it directly from the Shopify module.

### Status mapping

Map the platform's status values to Sophia's status strings. Sophia uses: `"pending"`, `"confirmed"`, `"shipped"`, `"delivered"`, `"cancelled"`.

```python
def _map_acme_status(status: str | None) -> str:
    mapping = {
        "new": "pending",
        "processing": "confirmed",
        "shipped": "shipped",
        "complete": "delivered",
        "canceled": "cancelled",
    }
    return mapping.get(status or "", "pending")
```

### Not-supported stub

For service methods that the platform's MCP server doesn't support, use a stub:

```python
def _not_supported(method_name: str):
    def _raise(**kwargs):
        raise NotImplementedError(
            f"'{method_name}' is not supported by the Acme MCP server. "
            f"Options: (1) implement it in a custom mapping module, "
            f"(2) use the generic REST adapter to call the Acme API directly, "
            f"or (3) submit a feature request to the MCP server maintainer."
        )
    return _raise
```

## Step 3: Write Parse Functions

Parse functions convert an `MCPToolResult` into one of Sophia's data models. Each function should:

1. Call `_extract_json(result)` to get the raw dict
2. Map platform-specific field names to Sophia's field names
3. Handle missing fields with sensible defaults
4. Return the appropriate Sophia dataclass

### Sophia's data models

The models you need to return are defined in `sophia/services/models.py`:

- **Orders:** `Order`, `OrderItem`, `OrderStatus`, `CancellationResult`
- **Customers:** `Customer`
- **Shipping:** `ShipmentTracking`, `ShippingOption`, `AddressUpdateResult`, `ReturnLabel`
- **Inventory:** `ProductDetails`, `ProductStock`, `WarrantyStatus`
- **Compensation:** `RefundResult`, `DiscountResult`, `FreeShippingResult`, `CouponResult`, `ReturnInitiationResult`, `ReturnStatus`

### Example: Parsing an order

```python
from sophia.services.models import Order, OrderItem, Address


def _parse_acme_order(result: MCPToolResult) -> Order:
    data = _extract_json(result)

    items = []
    for li in data.get("items", []):
        items.append(
            OrderItem(
                product_id=str(li.get("sku", "")),
                name=li.get("name", ""),
                quantity=li.get("qty", 1),
                unit_price=float(li.get("unit_price", 0)),
                total_price=float(li.get("unit_price", 0)) * li.get("qty", 1),
            )
        )

    shipping_address = None
    if addr := data.get("address"):
        shipping_address = Address(
            line1=addr.get("street", ""),
            line2=addr.get("street2"),
            city=addr.get("city", ""),
            state=addr.get("region", ""),
            postal_code=addr.get("postcode", ""),
            country=addr.get("country", "US"),
        )

    return Order(
        order_id=str(data.get("id", "")),
        customer_id=str(data.get("customer_id", "")),
        status=_map_acme_status(data.get("status")),
        items=items,
        total=float(data.get("grand_total", 0)),
        currency=data.get("currency", "USD"),
        created_at=_parse_datetime(data.get("created_at")),
        updated_at=_parse_datetime(data.get("updated_at")),
        shipping_address=shipping_address,
        tracking_number=data.get("tracking_number"),
    )
```

## Step 4: Write the Mapping Functions

Each mapping function returns a dict that maps Sophia's service method names to MCP tool configurations.

### Order mapping

```python
def acme_order_mapping() -> dict:
    return {
        "get_order": {
            "tool_name": "orders/get",
            "build_args": lambda order_id: {"id": order_id},
            "parse_response": _parse_acme_order,
        },
        "get_order_status": {
            "tool_name": "orders/get",
            "build_args": lambda order_id: {"id": order_id},
            "parse_response": _parse_acme_order_status,
        },
        "search_orders_by_customer": {
            "tool_name": "orders/search",
            "build_args": lambda customer_id, limit=20: {
                "customer_id": customer_id,
                "limit": limit,
            },
            "parse_response": _parse_acme_orders,
        },
        "cancel_order": {
            "tool_name": "orders/cancel",
            "build_args": lambda order_id, reason: {
                "id": order_id,
                "reason": reason,
            },
            "parse_response": _parse_acme_cancellation,
        },
        "update_order": {
            "tool_name": "orders/update",
            "build_args": _not_supported("update_order"),
            "parse_response": lambda r: None,
        },
        "place_order": {
            "tool_name": "orders/create",
            "build_args": _not_supported("place_order"),
            "parse_response": lambda r: None,
        },
    }
```

The method names (`get_order`, `get_order_status`, etc.) must match exactly what the corresponding MCP service class calls. Check the five service classes in `sophia/services/mcp/` for the complete list:

| Service | Methods |
|---------|---------|
| `order_service.py` | `get_order`, `get_order_status`, `search_orders_by_customer`, `cancel_order`, `update_order`, `place_order` |
| `customer_service.py` | `get_customer`, `search_customers`, `get_customer_history` |
| `shipping_service.py` | `track_shipment`, `get_shipping_options`, `update_shipping_address`, `generate_return_label` |
| `inventory_service.py` | `check_stock`, `get_product_details`, `check_warranty_status` |
| `compensation_service.py` | `process_full_refund`, `process_partial_refund`, `apply_discount`, `apply_free_shipping`, `generate_coupon`, `initiate_return`, `check_return_status` |

Every method must have an entry in the mapping dict. If the platform doesn't support a method, use `_not_supported`.

## Step 5: Register the Platform

Add your platform to the `PLATFORM_MAPPINGS` dict in `sophia/services/registry.py`:

```python
PLATFORM_MAPPINGS: dict[str, str] = {
    "shopify": "sophia.services.mcp.shopify_mapping",
    "acme": "sophia.services.mcp.acme_mapping",
}
```

## Step 6: Configure a Hat to Use Your Platform

In your Hat's `hat.json`, set a service backend to use MCP with your platform:

```json
{
  "backends": {
    "order": {
      "provider": "mcp",
      "config": {
        "server_url": "https://acme-mcp.example.com",
        "server_name": "acme",
        "auth_token_env": "ACME_MCP_TOKEN",
        "platform": "acme"
      }
    }
  }
}
```

The `auth_token_env` key means the actual token is read from the `ACME_MCP_TOKEN` environment variable at startup (the `_env` suffix is resolved automatically by the registry).

## Step 7: Write Tests

Create `tests/services/mcp/test_acme_mapping.py`. Test each parse function with realistic sample data from the platform.

```python
import json
import pytest
from sophia.services.mcp.models import MCPToolResult
from sophia.services.mcp.acme_mapping import (
    _parse_acme_order,
    _map_acme_status,
)


def _wrap(data: dict) -> MCPToolResult:
    return MCPToolResult(content=[{"type": "text", "text": json.dumps(data)}])


class TestParseAcmeOrder:
    def test_full_order(self):
        data = {
            "id": 12345,
            "customer_id": 6789,
            "status": "shipped",
            "items": [
                {"sku": "A1", "name": "Widget", "qty": 2, "unit_price": 9.99}
            ],
            "grand_total": 19.98,
            "currency": "USD",
            "created_at": "2025-01-15T10:00:00Z",
            "updated_at": "2025-01-16T12:00:00Z",
        }
        order = _parse_acme_order(_wrap(data))
        assert order.order_id == "12345"
        assert order.status == "shipped"
        assert len(order.items) == 1

    def test_minimal_order(self):
        data = {"id": 1, "customer_id": 1, "grand_total": 0}
        order = _parse_acme_order(_wrap(data))
        assert order.order_id == "1"
        assert order.status == "pending"


class TestMapAcmeStatus:
    def test_known_statuses(self):
        assert _map_acme_status("new") == "pending"
        assert _map_acme_status("shipped") == "shipped"

    def test_unknown_defaults_to_pending(self):
        assert _map_acme_status("something_new") == "pending"
```

Run the tests:

```bash
uv run pytest tests/services/mcp/test_acme_mapping.py -v
```

## Checklist

Before submitting your platform mapping:

- [ ] All five `<platform>_<service>_mapping()` functions exist and return complete dicts
- [ ] Every service method has an entry (supported methods have real implementations, unsupported ones use `_not_supported`)
- [ ] Parse functions handle missing/optional fields gracefully with defaults
- [ ] Platform is registered in `PLATFORM_MAPPINGS` in `registry.py`
- [ ] Tests cover each parse function with realistic platform data
- [ ] `uv run pytest` passes with no failures
- [ ] `uv run ruff check` passes with no errors
- [ ] No changes to `MCPServiceAdapter`, the five MCP service classes, or any Hat files

## Reference

- [Shopify mapping](../sophia/services/mcp/shopify_mapping.py) — complete reference implementation
- [MCP adapter](../sophia/services/mcp/adapter.py) — base adapter class
- [Service models](../sophia/services/models.py) — Sophia's data models
- [Service registry](../sophia/services/registry.py) — how platforms are resolved
- [Creating Hats](CREATING_HATS.md) — how Hats configure backends
