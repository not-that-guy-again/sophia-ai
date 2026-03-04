import re

from sophia.auth.keys import generate_key, hash_key


def test_generate_key_format():
    full_key, record = generate_key("test-tenant")
    assert re.match(r"sk-sophia-test-tenant-[0-9a-f]{32}", full_key)
    assert record.tenant_id == "test-tenant"
    assert record.key_hash == hash_key(full_key)
    assert record.is_active is True
    assert "chat" in record.scopes
    assert "admin" in record.scopes


def test_hash_key_consistent():
    key = "sk-sophia-test-abc123"
    h1 = hash_key(key)
    h2 = hash_key(key)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_generate_key_custom_scopes():
    full_key, record = generate_key("tenant", scopes=["chat"])
    assert record.scopes == ["chat"]


def test_different_keys_different_hashes():
    _, r1 = generate_key("tenant1")
    _, r2 = generate_key("tenant2")
    assert r1.key_hash != r2.key_hash
