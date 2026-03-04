from unittest.mock import AsyncMock

import pytest

from sophia.services.mcp.adapter import MCPServiceAdapter
from sophia.services.mcp.models import MCPToolDefinition, MCPToolResult


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client._tools = {
        "get_order": MCPToolDefinition(
            name="get_order",
            description="Get order",
            input_schema={},
        ),
        "cancel_order": MCPToolDefinition(
            name="cancel_order",
            description="Cancel order",
            input_schema={},
        ),
    }
    return client


@pytest.fixture
def sample_mapping():
    return {
        "get_order": {
            "tool_name": "get_order",
            "build_args": lambda order_id: {"order_id": order_id},
            "parse_response": lambda r: {
                "order_id": "123",
                "parsed": True,
            },
        },
        "cancel_order": {
            "tool_name": "cancel_order",
            "build_args": lambda order_id, reason: {
                "order_id": order_id,
                "reason": reason,
            },
            "parse_response": lambda r: {"cancelled": True},
        },
    }


@pytest.mark.asyncio
async def test_adapter_call_success(mock_client, sample_mapping):
    mock_client.call_tool.return_value = MCPToolResult(
        content=[{"type": "text", "text": '{"order_id": "123"}'}],
        is_error=False,
    )
    adapter = MCPServiceAdapter(mock_client, sample_mapping)

    result = await adapter._call("get_order", order_id="123")

    assert result == {"order_id": "123", "parsed": True}
    mock_client.call_tool.assert_called_once_with("get_order", {"order_id": "123"})


@pytest.mark.asyncio
async def test_adapter_call_error(mock_client, sample_mapping):
    mock_client.call_tool.return_value = MCPToolResult(
        content=[{"type": "text", "text": "Not found"}],
        is_error=True,
    )
    adapter = MCPServiceAdapter(mock_client, sample_mapping)

    result = await adapter._call("get_order", order_id="bad")

    assert result is None


@pytest.mark.asyncio
async def test_adapter_call_unmapped_method(mock_client, sample_mapping):
    adapter = MCPServiceAdapter(mock_client, sample_mapping)

    with pytest.raises(NotImplementedError, match="no_such_method"):
        await adapter._call("no_such_method")


def test_validate_mapping_all_present(mock_client, sample_mapping):
    adapter = MCPServiceAdapter(mock_client, sample_mapping)

    missing = adapter.validate_mapping()

    assert missing == []


def test_validate_mapping_missing_tools(mock_client):
    mapping = {
        "get_order": {
            "tool_name": "get_order",
            "build_args": lambda: {},
            "parse_response": lambda r: None,
        },
        "unknown_op": {
            "tool_name": "nonexistent_tool",
            "build_args": lambda: {},
            "parse_response": lambda r: None,
        },
    }
    adapter = MCPServiceAdapter(mock_client, mapping)

    missing = adapter.validate_mapping()

    assert missing == ["nonexistent_tool"]


@pytest.mark.asyncio
async def test_adapter_custom_error_handler(mock_client):
    custom_handler_called = False

    def custom_error_handler(result):
        nonlocal custom_handler_called
        custom_handler_called = True
        return {"error": True, "text": result.content[0]["text"]}

    mapping = {
        "get_order": {
            "tool_name": "get_order",
            "build_args": lambda order_id: {"order_id": order_id},
            "parse_response": lambda r: None,
            "error_handler": custom_error_handler,
        },
    }
    mock_client.call_tool.return_value = MCPToolResult(
        content=[{"type": "text", "text": "Custom error"}],
        is_error=True,
    )
    adapter = MCPServiceAdapter(mock_client, mapping)

    result = await adapter._call("get_order", order_id="123")

    assert custom_handler_called
    assert result == {"error": True, "text": "Custom error"}
