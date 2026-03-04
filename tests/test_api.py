"""Test the FastAPI endpoints."""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from sophia.main import app
from sophia.api import routes
from sophia.core.input_gate import Intent
from sophia.core.proposer import Proposal, CandidateAction
from sophia.core.executor import ExecutionResult
from sophia.core.loop import PipelineResult
from sophia.core.risk_classifier import RiskClassification
from sophia.tools.base import ToolResult


@pytest.fixture(autouse=True)
def reset_agent_loop():
    """Reset the global agent loop between tests."""
    routes._agent_loop = None
    yield
    routes._agent_loop = None


client = TestClient(app)


def test_health():
    # Health endpoint checks DB connectivity; init an in-memory DB
    import asyncio
    from sophia.audit.database import init_db, close_db
    from sophia.config import Settings as _Settings

    loop = asyncio.new_event_loop()
    loop.run_until_complete(
        init_db(_Settings(database_url="sqlite+aiosqlite:///:memory:"))
    )
    try:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert "checks" in data
    finally:
        loop.run_until_complete(close_db())
        loop.close()


def test_tools_endpoint():
    """Tools endpoint returns tools from the equipped hat."""
    response = client.get("/tools")
    assert response.status_code == 200
    tools = response.json()
    assert len(tools) == 20
    names = {t["name"] for t in tools}
    assert "look_up_order" in names
    assert "offer_full_refund" in names
    assert "escalate_to_human" in names


def test_hats_endpoint():
    """List available hats."""
    response = client.get("/hats")
    assert response.status_code == 200
    hats = response.json()
    assert len(hats) >= 1
    names = {h["name"] for h in hats}
    assert "customer-service" in names


def test_active_hat_endpoint():
    """Get the currently equipped hat."""
    response = client.get("/hats/active")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "customer-service"
    assert data["display_name"] == "Customer Service"
    assert len(data["tools"]) == 19
    assert data["stakeholder_count"] == 4


def test_chat_endpoint():
    """Test /chat with a mocked agent loop."""
    mock_result = PipelineResult(
        intent=Intent(
            action_requested="order_status",
            target="ORD-12345",
            parameters={},
            raw_message="Where is my order #12345?",
            hat_name="customer-service",
        ),
        proposal=Proposal(
            intent=Intent(
                action_requested="order_status",
                target="ORD-12345",
                parameters={},
                raw_message="Where is my order #12345?",
                hat_name="customer-service",
            ),
            candidates=[
                CandidateAction(
                    tool_name="check_order_status",
                    parameters={"order_id": "ORD-12345"},
                    reasoning="Customer wants order status",
                    expected_outcome="Return order status info",
                )
            ],
        ),
        consequence_trees=[],
        evaluation_results=[],
        risk_classification=RiskClassification(
            tier="GREEN",
            weighted_score=0.0,
            explanation="No consequence tree generated.",
        ),
        execution=ExecutionResult(
            action_taken=CandidateAction(
                tool_name="check_order_status",
                parameters={"order_id": "ORD-12345"},
                reasoning="Customer wants order status",
                expected_outcome="Return order status info",
            ),
            tool_result=ToolResult(
                success=True,
                data={"order_id": "ORD-12345", "status": "delivered"},
                message="Status for ORD-12345: delivered",
            ),
            risk_tier="GREEN",
        ),
        response="Status for ORD-12345: delivered",
        metadata={"hat": "customer-service"},
    )

    with patch.object(routes, "get_agent_loop") as mock_get_loop:
        mock_loop = AsyncMock()
        mock_loop.process.return_value = mock_result
        mock_get_loop.return_value = mock_loop  # AsyncMock auto-handles await

        response = client.post("/chat", json={"message": "Where is my order #12345?"})

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Status for ORD-12345: delivered"
    assert data["intent"]["action_requested"] == "order_status"
    assert data["intent"]["hat_name"] == "customer-service"
    assert data["execution"]["risk_tier"] == "GREEN"
