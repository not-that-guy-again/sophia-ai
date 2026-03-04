import json

import httpx
import pytest

from sophia.services.mcp.client import MCPClient
from sophia.services.mcp.exceptions import (
    MCPConnectionError,
    MCPToolNotFoundError,
    MCPTimeoutError,
)


def _make_jsonrpc_response(result: dict, request_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _make_mock_transport(responses: list[dict]) -> httpx.MockTransport:
    """Create a mock transport that returns responses in order."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        json.loads(request.content)  # validate JSON
        idx = min(call_count, len(responses) - 1)
        call_count += 1
        resp = responses[idx]
        if isinstance(resp, Exception):
            raise resp
        return httpx.Response(200, json=resp)

    return httpx.MockTransport(handler)


def _standard_init_and_tools_responses() -> list[dict]:
    """Standard responses for initialize + tools/list."""
    return [
        _make_jsonrpc_response(
            {"protocolVersion": "2024-11-05", "serverInfo": {"name": "test-server"}},
            request_id=1,
        ),
        _make_jsonrpc_response(
            {
                "tools": [
                    {
                        "name": "get_order",
                        "description": "Get an order by ID",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"order_id": {"type": "string"}},
                        },
                    },
                    {
                        "name": "cancel_order",
                        "description": "Cancel an order",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "order_id": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                        },
                    },
                ]
            },
            request_id=2,
        ),
    ]


@pytest.fixture
def mock_client():
    """Create an MCPClient with a mock transport that handles init + tools/list."""
    responses = _standard_init_and_tools_responses()
    transport = _make_mock_transport(responses)
    client = MCPClient(
        server_url="http://test-server:8080",
        server_name="test-server",
    )
    client._http_client = httpx.AsyncClient(
        base_url="http://test-server:8080",
        transport=transport,
        timeout=30.0,
    )
    return client


@pytest.mark.asyncio
async def test_connect_discovers_tools(mock_client: MCPClient):
    server_info = await mock_client.connect()

    assert server_info.name == "test-server"
    assert server_info.url == "http://test-server:8080"
    assert len(server_info.tools) == 2
    assert server_info.tools[0].name == "get_order"
    assert server_info.tools[1].name == "cancel_order"
    assert mock_client.is_connected is True

    tools = await mock_client.list_tools()
    assert len(tools) == 2


@pytest.mark.asyncio
async def test_call_tool_success():
    responses = _standard_init_and_tools_responses()
    responses.append(
        _make_jsonrpc_response(
            {
                "content": [{"type": "text", "text": '{"order_id": "123", "status": "pending"}'}],
                "isError": False,
            },
            request_id=3,
        )
    )
    transport = _make_mock_transport(responses)
    client = MCPClient(server_url="http://test-server:8080", server_name="test-server")
    client._http_client = httpx.AsyncClient(
        base_url="http://test-server:8080", transport=transport, timeout=30.0
    )

    await client.connect()
    result = await client.call_tool("get_order", {"order_id": "123"})

    assert result.is_error is False
    assert len(result.content) == 1
    assert result.content[0]["type"] == "text"
    assert "123" in result.content[0]["text"]

    await client.close()


@pytest.mark.asyncio
async def test_call_tool_error():
    responses = _standard_init_and_tools_responses()
    responses.append(
        _make_jsonrpc_response(
            {
                "content": [{"type": "text", "text": "Order not found"}],
                "isError": True,
            },
            request_id=3,
        )
    )
    transport = _make_mock_transport(responses)
    client = MCPClient(server_url="http://test-server:8080", server_name="test-server")
    client._http_client = httpx.AsyncClient(
        base_url="http://test-server:8080", transport=transport, timeout=30.0
    )

    await client.connect()
    result = await client.call_tool("get_order", {"order_id": "nonexistent"})

    assert result.is_error is True
    assert result.content[0]["text"] == "Order not found"

    await client.close()


@pytest.mark.asyncio
async def test_call_unknown_tool_raises(mock_client: MCPClient):
    await mock_client.connect()

    with pytest.raises(MCPToolNotFoundError, match="unknown_tool"):
        await mock_client.call_tool("unknown_tool", {})

    await mock_client.close()


@pytest.mark.asyncio
async def test_close_cleans_up(mock_client: MCPClient):
    await mock_client.connect()
    assert mock_client.is_connected is True

    await mock_client.close()
    assert mock_client.is_connected is False
    assert mock_client._http_client is None


@pytest.mark.asyncio
async def test_connection_failure():
    def error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    transport = httpx.MockTransport(error_handler)
    client = MCPClient(server_url="http://bad-server:8080", server_name="bad-server")
    client._http_client = httpx.AsyncClient(
        base_url="http://bad-server:8080", transport=transport, timeout=30.0
    )

    with pytest.raises(MCPConnectionError, match="Connection error"):
        await client.connect()

    await client.close()


@pytest.mark.asyncio
async def test_timeout_raises():
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timed out")

    transport = httpx.MockTransport(timeout_handler)
    client = MCPClient(server_url="http://slow-server:8080", server_name="slow-server")
    client._http_client = httpx.AsyncClient(
        base_url="http://slow-server:8080", transport=transport, timeout=30.0
    )

    with pytest.raises(MCPTimeoutError, match="Timeout"):
        await client.connect()

    await client.close()
