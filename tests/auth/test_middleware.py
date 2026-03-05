"""Tests for auth middleware using FastAPI TestClient."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from sophia.auth.keys import hash_key
from sophia.auth.middleware import require_auth, require_scope
from sophia.auth.models import APIKeyRecord


def _make_key_record(
    scopes=None,
    is_active=True,
    expires_at=None,
    rate_limit_rpm=60,
) -> APIKeyRecord:
    record = APIKeyRecord()
    record.key_id = "test-key-id"
    record.key_hash = hash_key("sk-sophia-test-abc123")
    record.tenant_id = "test-tenant"
    record.hat_name = "customer-service"
    record.scopes = scopes or ["chat", "admin"]
    record.rate_limit_rpm = rate_limit_rpm
    record.created_at = datetime.now(UTC)
    record.expires_at = expires_at
    record.is_active = is_active
    return record


def _make_test_app():
    app = FastAPI()

    @app.get("/protected")
    async def protected(key=Depends(require_auth)):
        return {"tenant": key.tenant_id}

    @app.get("/chat-only")
    async def chat_only(key=Depends(require_scope("chat"))):
        return {"ok": True}

    @app.get("/admin-only")
    async def admin_only(key=Depends(require_scope("admin"))):
        return {"ok": True}

    return app


@pytest.fixture
def app():
    return _make_test_app()


@pytest.fixture
def client(app):
    return TestClient(app)


def test_require_auth_valid_key(client):
    record = _make_key_record()
    with patch("sophia.auth.middleware.lookup_key", new_callable=AsyncMock, return_value=record):
        resp = client.get("/protected", headers={"Authorization": "Bearer sk-sophia-test-abc123"})
    assert resp.status_code == 200
    assert resp.json()["tenant"] == "test-tenant"


def test_require_auth_missing_header(client):
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_require_auth_invalid_key(client):
    with patch("sophia.auth.middleware.lookup_key", new_callable=AsyncMock, return_value=None):
        resp = client.get("/protected", headers={"Authorization": "Bearer bad-key"})
    assert resp.status_code == 401


def test_require_auth_expired_key(client):
    record = _make_key_record(expires_at=datetime.now(UTC) - timedelta(hours=1))
    with patch("sophia.auth.middleware.lookup_key", new_callable=AsyncMock, return_value=record):
        resp = client.get("/protected", headers={"Authorization": "Bearer sk-sophia-test-abc123"})
    assert resp.status_code == 401


def test_require_auth_revoked_key(client):
    record = _make_key_record(is_active=False)
    with patch("sophia.auth.middleware.lookup_key", new_callable=AsyncMock, return_value=record):
        resp = client.get("/protected", headers={"Authorization": "Bearer sk-sophia-test-abc123"})
    assert resp.status_code == 401


def test_require_scope_pass(client):
    record = _make_key_record(scopes=["chat", "admin"])
    with patch("sophia.auth.middleware.lookup_key", new_callable=AsyncMock, return_value=record):
        resp = client.get("/chat-only", headers={"Authorization": "Bearer sk-sophia-test-abc123"})
    assert resp.status_code == 200


def test_require_scope_fail(client):
    record = _make_key_record(scopes=["chat"])
    with patch("sophia.auth.middleware.lookup_key", new_callable=AsyncMock, return_value=record):
        resp = client.get("/admin-only", headers={"Authorization": "Bearer sk-sophia-test-abc123"})
    assert resp.status_code == 403


def test_rate_limiter_exceeded(client):
    record = _make_key_record(rate_limit_rpm=2)
    with patch("sophia.auth.middleware.lookup_key", new_callable=AsyncMock, return_value=record):
        # Reset the rate limiter
        from sophia.auth import middleware

        middleware._rate_limiter._windows.clear()

        client.get("/protected", headers={"Authorization": "Bearer sk-sophia-test-abc123"})
        client.get("/protected", headers={"Authorization": "Bearer sk-sophia-test-abc123"})
        resp = client.get("/protected", headers={"Authorization": "Bearer sk-sophia-test-abc123"})
    assert resp.status_code == 429
