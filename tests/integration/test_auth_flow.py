"""Integration test: API key lifecycle — create, authenticate, revoke.

Uses in-memory SQLite for the auth database. No real HTTP calls.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sophia.api.admin_routes import admin_router
from sophia.audit.database import close_db, init_db
from sophia.auth.keys import generate_key
from sophia.auth.middleware import require_scope
from sophia.config import Settings


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def db():
    test_settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    await init_db(test_settings)
    yield
    await close_db()


@pytest.fixture
def admin_key(db):
    """Create an admin key and store it in the test DB."""
    import asyncio

    from sophia.audit.database import get_session

    full_key, record = generate_key("test-admin", scopes=["admin", "chat"])

    async def _store():
        async with get_session() as session:
            session.add(record)
            await session.commit()

    asyncio.get_event_loop().run_until_complete(_store())
    return full_key


@pytest.fixture
def app(db):
    from fastapi import APIRouter, Depends

    test_app = FastAPI()
    test_app.include_router(admin_router)

    # Add a protected endpoint for testing auth
    protected_router = APIRouter()

    @protected_router.get("/protected")
    async def protected(key=Depends(require_scope("chat"))):
        return {"tenant_id": key.tenant_id, "scopes": key.scopes}

    test_app.include_router(protected_router)
    return test_app


@pytest.fixture
def client(app, admin_key):
    c = TestClient(app)
    c.headers["Authorization"] = f"Bearer {admin_key}"
    return c


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_key_lifecycle(app, client, admin_key):
    """Create a key, use it, revoke it, verify it no longer works."""
    # 1. Create a new key (same tenant as admin for tenant-scoped operations)
    resp = client.post(
        "/admin/keys",
        json={
            "tenant_id": "test-admin",
            "scopes": ["chat"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    new_key = data["key"]
    new_key_id = data["key_id"]
    assert new_key.startswith("sk-sophia-test-admin-")

    # 2. Use the new key to access a protected endpoint
    resp = client.get("/protected", headers={"Authorization": f"Bearer {new_key}"})
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "test-admin"

    # 3. Revoke the key
    resp = client.delete(f"/admin/keys/{new_key_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"

    # 4. Verify the revoked key is rejected
    resp = client.get("/protected", headers={"Authorization": f"Bearer {new_key}"})
    assert resp.status_code == 401
    assert "revoked" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_missing_auth_header(app):
    """Requests without Authorization header are rejected."""
    unauth_client = TestClient(app)
    resp = unauth_client.get("/protected")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_key(app):
    """Requests with an invalid key are rejected."""
    unauth_client = TestClient(app)
    unauth_client.headers["Authorization"] = "Bearer sk-sophia-fake-000000"
    resp = unauth_client.get("/protected")
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_scope_enforcement(app, client, admin_key):
    """Key without required scope is rejected with 403."""
    # Create a key with only "chat" scope (no "admin")
    resp = client.post(
        "/admin/keys",
        json={
            "tenant_id": "limited-tenant",
            "scopes": ["chat"],
        },
    )
    limited_key = resp.json()["key"]

    # Try to access admin endpoint with chat-only key
    resp = client.get("/admin/keys", headers={"Authorization": f"Bearer {limited_key}"})
    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"]
