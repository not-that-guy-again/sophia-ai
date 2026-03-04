"""Tests for the enhanced /health endpoint."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sophia.api.routes import router
from sophia.audit.database import close_db, init_db
from sophia.config import Settings


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router)
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
async def db():
    test_settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    await init_db(test_settings)
    yield
    await close_db()


@pytest.mark.asyncio
async def test_health_check_ok(client, db):
    """Health returns 200/ok when DB is reachable."""
    # DB is initialized via fixture, no agent loop so hat/services show "none"
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["hat"] == "none"
    assert data["checks"]["services"] == "none"


@pytest.mark.asyncio
async def test_health_check_degraded(client):
    """Health returns 503/degraded when DB is not initialized."""
    # No DB init — engine is None, should be degraded
    # Ensure engine is None by patching
    with patch("sophia.api.routes._agent_loop", None), \
         patch("sophia.audit.database._engine", None):
        resp = client.get("/health")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["checks"]["database"] == "unavailable"
