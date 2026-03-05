"""Integration test: MCP adapter end-to-end.

Exercises the full path: MCPClient → MCPServiceAdapter → MCPOrderService
with a mock MCP server (httpx.MockTransport). No real HTTP calls.
"""

import json

import httpx
import pytest

from sophia.services.mcp.client import MCPClient
from sophia.services.mcp.order_service import MCPOrderService
from sophia.services.mcp.shopify_mapping import shopify_order_mapping


# ── Fake MCP server ─────────────────────────────────────────────────────────

TOOLS_LIST = [
    {"name": "get_order", "description": "Look up an order", "inputSchema": {}},
    {"name": "list_orders", "description": "Search orders", "inputSchema": {}},
    {"name": "cancel_order", "description": "Cancel an order", "inputSchema": {}},
]

ORDER_JSON = json.dumps(
    {
        "id": 12345,
        "name": "#1001",
        "email": "cust@example.com",
        "created_at": "2025-01-15T10:00:00Z",
        "updated_at": "2025-01-15T10:00:00Z",
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
        "total_price": "79.99",
        "currency": "USD",
        "customer": {
            "id": 100,
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "cust@example.com",
        },
        "line_items": [
            {
                "id": 1,
                "title": "Widget",
                "quantity": 2,
                "price": "39.99",
                "sku": "WGT-001",
                "product_id": "PROD-1",
            }
        ],
        "shipping_address": {
            "address1": "123 Main St",
            "city": "Anytown",
            "province": "CA",
            "country": "US",
            "zip": "90210",
        },
    }
)


def _fake_mcp_handler(request: httpx.Request) -> httpx.Response:
    """Simulate an MCP JSON-RPC server."""
    body = json.loads(request.content)
    method = body.get("method")
    req_id = body.get("id")

    if method == "initialize":
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"protocolVersion": "2024-11-05"},
            },
        )

    if method == "tools/list":
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS_LIST},
            },
        )

    if method == "tools/call":
        tool_name = body["params"]["name"]
        if tool_name == "get_order":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": ORDER_JSON}],
                        "isError": False,
                    },
                },
            )

    return httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": "Method not found"},
        },
    )


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.fixture
async def mcp_client():
    """Create an MCPClient backed by a mock transport."""
    transport = httpx.MockTransport(_fake_mcp_handler)
    client = MCPClient(
        server_url="http://shopify-mcp.local",
        server_name="shopify",
    )
    # Inject mock transport
    client._http_client = httpx.AsyncClient(
        transport=transport,
        base_url="http://shopify-mcp.local",
    )
    await client.connect()
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_mcp_client_connect_and_discover(mcp_client: MCPClient):
    """Verify connect discovers tools from the fake server."""
    assert mcp_client.is_connected
    tools = await mcp_client.list_tools()
    assert len(tools) == 3
    tool_names = {t.name for t in tools}
    assert "get_order" in tool_names


@pytest.mark.asyncio
async def test_mcp_order_service_get_order(mcp_client: MCPClient):
    """Full path: MCPOrderService → adapter → client → fake server → parsed Order."""
    mapping = shopify_order_mapping()
    svc = MCPOrderService(client=mcp_client, tool_mapping=mapping)

    order = await svc.get_order("12345")

    assert order is not None
    assert order.order_id == "12345"
    assert order.customer_id == "100"
    assert order.status == "shipped"
    assert order.total == 79.99
    assert len(order.items) == 1
    assert order.items[0].name == "Widget"
    assert order.items[0].quantity == 2


@pytest.mark.asyncio
async def test_mcp_adapter_validate_mapping(mcp_client: MCPClient):
    """Validate mapping reports missing tools correctly."""
    mapping = shopify_order_mapping()
    from sophia.services.mcp.adapter import MCPServiceAdapter

    adapter = MCPServiceAdapter(client=mcp_client, tool_mapping=mapping)
    missing = adapter.validate_mapping()
    # get_order is present, but other tools in the mapping may not be
    assert "get_order" not in missing
