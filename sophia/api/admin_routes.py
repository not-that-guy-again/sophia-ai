"""Admin API routes for key management."""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from sophia.auth.keys import generate_key
from sophia.auth.middleware import require_scope
from sophia.audit.database import get_session
from sophia.auth.models import APIKeyRecord

from sqlalchemy import select, update

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/admin", tags=["admin"])


class CreateKeyRequest(BaseModel):
    tenant_id: str
    hat_name: str = "customer-service"
    scopes: list[str] = ["chat"]
    rate_limit_rpm: int = 60


class CreateKeyResponse(BaseModel):
    key: str
    key_id: str
    tenant_id: str
    scopes: list[str]


class KeySummary(BaseModel):
    key_id: str
    tenant_id: str
    hat_name: str
    scopes: list[str]
    rate_limit_rpm: int
    created_at: datetime
    expires_at: datetime | None
    is_active: bool


@admin_router.post("/keys", response_model=CreateKeyResponse)
async def create_key(
    request: CreateKeyRequest,
    _key=Depends(require_scope("admin")),
):
    """Create a new API key."""
    full_key, record = generate_key(
        tenant_id=request.tenant_id,
        hat_name=request.hat_name,
        scopes=request.scopes,
    )
    record.rate_limit_rpm = request.rate_limit_rpm

    async with get_session() as session:
        session.add(record)
        await session.commit()

    logger.info("Created API key %s for tenant %s", record.key_id, request.tenant_id)
    return CreateKeyResponse(
        key=full_key,
        key_id=record.key_id,
        tenant_id=record.tenant_id,
        scopes=record.scopes,
    )


@admin_router.get("/keys", response_model=list[KeySummary])
async def list_keys(
    _key=Depends(require_scope("admin")),
):
    """List API keys for the authenticated tenant."""
    async with get_session() as session:
        result = await session.execute(
            select(APIKeyRecord).where(
                APIKeyRecord.tenant_id == _key.tenant_id
            )
        )
        records = result.scalars().all()

    return [
        KeySummary(
            key_id=r.key_id,
            tenant_id=r.tenant_id,
            hat_name=r.hat_name,
            scopes=r.scopes,
            rate_limit_rpm=r.rate_limit_rpm,
            created_at=r.created_at,
            expires_at=r.expires_at,
            is_active=r.is_active,
        )
        for r in records
    ]


@admin_router.delete("/keys/{key_id}")
async def revoke_key(
    key_id: str,
    _key=Depends(require_scope("admin")),
):
    """Revoke an API key."""
    async with get_session() as session:
        result = await session.execute(
            select(APIKeyRecord).where(
                APIKeyRecord.key_id == key_id,
                APIKeyRecord.tenant_id == _key.tenant_id,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise HTTPException(status_code=404, detail="Key not found")

        await session.execute(
            update(APIKeyRecord)
            .where(APIKeyRecord.key_id == key_id)
            .values(is_active=False)
        )
        await session.commit()

    logger.info("Revoked API key %s", key_id)
    return {"status": "revoked", "key_id": key_id}
