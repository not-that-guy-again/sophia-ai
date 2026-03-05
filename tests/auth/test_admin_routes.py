"""Tests for admin routes with full database lifecycle."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sophia.api.admin_routes import admin_router
from sophia.audit.database import close_db, init_db
from sophia.auth.keys import generate_key
from sophia.config import Settings


@pytest.fixture
async def db():
    """Initialize and tear down an in-memory test database."""
    test_settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    await init_db(test_settings)
    yield
    await close_db()


@pytest.fixture
def app(db):
    test_app = FastAPI()
    test_app.include_router(admin_router)
    return test_app


@pytest.fixture
def admin_key(db):
    """Create an admin key in the database and return the full key."""
    import asyncio

    from sophia.audit.database import get_session

    full_key, record = generate_key("test-tenant", scopes=["admin", "chat"])

    async def _store():
        async with get_session() as session:
            session.add(record)
            await session.commit()

    asyncio.get_event_loop().run_until_complete(_store())
    return full_key


@pytest.fixture
def client(app, admin_key):
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {admin_key}"
    return c


@pytest.mark.asyncio
async def test_admin_create_key(client):
    resp = client.post(
        "/admin/keys",
        json={
            "tenant_id": "new-tenant",
            "scopes": ["chat"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == "new-tenant"
    assert data["scopes"] == ["chat"]
    assert data["key"].startswith("sk-sophia-new-tenant-")


@pytest.mark.asyncio
async def test_admin_list_keys(client):
    # Create a key first
    client.post("/admin/keys", json={"tenant_id": "test-tenant", "scopes": ["chat"]})

    resp = client.get("/admin/keys")
    assert resp.status_code == 200
    keys = resp.json()
    assert len(keys) >= 1
    assert any(k["tenant_id"] == "test-tenant" for k in keys)


@pytest.mark.asyncio
async def test_admin_revoke_key(client):
    # Create a key
    resp = client.post("/admin/keys", json={"tenant_id": "test-tenant", "scopes": ["chat"]})
    key_id = resp.json()["key_id"]

    # Revoke it
    resp = client.delete(f"/admin/keys/{key_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"

    # Verify it appears as inactive
    resp = client.get("/admin/keys")
    revoked = [k for k in resp.json() if k["key_id"] == key_id]
    assert len(revoked) == 1
    assert revoked[0]["is_active"] is False
