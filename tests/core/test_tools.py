import pytest

from sophia.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_look_up_order_found(tool_registry: ToolRegistry):
    result = await tool_registry.execute("look_up_order", {"order_id": "ORD-12345"})
    assert result.success
    assert result.data["order_id"] == "ORD-12345"
    assert result.data["customer_id"] == "CUST-001"


@pytest.mark.asyncio
async def test_look_up_order_normalizes_id(tool_registry: ToolRegistry):
    result = await tool_registry.execute("look_up_order", {"order_id": "#12345"})
    assert result.success
    assert result.data["order_id"] == "ORD-12345"


@pytest.mark.asyncio
async def test_look_up_order_not_found(tool_registry: ToolRegistry):
    result = await tool_registry.execute("look_up_order", {"order_id": "ORD-00000"})
    assert not result.success


@pytest.mark.asyncio
async def test_check_order_status(tool_registry: ToolRegistry):
    result = await tool_registry.execute("check_order_status", {"order_id": "ORD-12345"})
    assert result.success
    assert result.data["status"] == "delivered"


@pytest.mark.asyncio
async def test_partial_refund(tool_registry: ToolRegistry):
    result = await tool_registry.execute(
        "offer_partial_refund",
        {"order_id": "ORD-12345", "amount": 25.00, "reason": "damaged"},
    )
    assert result.success
    assert result.data["amount"] == 25.00
    assert result.data["status"] == "processed"


@pytest.mark.asyncio
async def test_escalation(tool_registry: ToolRegistry):
    result = await tool_registry.execute(
        "escalate_to_human",
        {
            "reason": "Customer threatening legal action",
            "priority": "urgent",
            "context_summary": "Customer wants $500 refund",
        },
    )
    assert result.success
    assert result.data["queue_position"] == 1


def test_hat_registers_all_tools(tool_registry: ToolRegistry):
    definitions = tool_registry.get_definitions()
    assert len(definitions) == 19
    names = {d["name"] for d in definitions}
    assert "look_up_order" in names
    assert "escalate_to_human" in names
    assert "offer_full_refund" in names


@pytest.mark.asyncio
async def test_registry_execute_unknown_tool():
    registry = ToolRegistry()
    result = await registry.execute("nonexistent_tool", {})
    assert not result.success
    assert "Unknown tool" in result.message
