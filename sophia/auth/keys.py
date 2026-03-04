import hashlib
import secrets
from datetime import UTC, datetime

from sqlalchemy import select

from sophia.auth.models import APIKeyRecord
from sophia.audit.database import get_session


def generate_key(tenant_id: str, hat_name: str = "customer-service", scopes: list[str] | None = None) -> tuple[str, APIKeyRecord]:
    """Generate a new API key.

    Returns (full_key, record_with_hash). The full key is only available at
    creation time — only the hash is stored.
    """
    random_hex = secrets.token_hex(16)
    full_key = f"sk-sophia-{tenant_id}-{random_hex}"
    key_id = secrets.token_hex(12)
    key_hash = hash_key(full_key)

    record = APIKeyRecord(
        key_id=key_id,
        key_hash=key_hash,
        tenant_id=tenant_id,
        hat_name=hat_name,
        scopes=scopes or ["chat", "admin"],
        rate_limit_rpm=60,
        created_at=datetime.now(UTC),
        is_active=True,
    )
    return full_key, record


def hash_key(raw_key: str) -> str:
    """SHA-256 hex digest of a raw API key."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def lookup_key(key_hash: str) -> APIKeyRecord | None:
    """Look up an API key record by hash."""
    async with get_session() as session:
        result = await session.execute(
            select(APIKeyRecord).where(APIKeyRecord.key_hash == key_hash)
        )
        return result.scalar_one_or_none()
