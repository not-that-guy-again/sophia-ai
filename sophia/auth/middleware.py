import logging
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request

from sophia.auth.keys import hash_key, lookup_key
from sophia.auth.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_rate_limiter = RateLimiter()


async def require_auth(request: Request) -> object:
    """FastAPI dependency: extract and validate Bearer token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    raw_key = auth_header[len("Bearer "):]
    if not raw_key:
        raise HTTPException(status_code=401, detail="Empty API key")

    key_hash_value = hash_key(raw_key)
    record = await lookup_key(key_hash_value)

    if record is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not record.is_active:
        raise HTTPException(status_code=401, detail="API key has been revoked")

    if record.expires_at and record.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=401, detail="API key has expired")

    if not _rate_limiter.check(record.key_id, record.rate_limit_rpm):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    request.state.api_key = record
    return record


def require_scope(scope: str):
    """Return a dependency that checks the API key has the given scope."""
    async def checker(key=Depends(require_auth)):
        if scope not in key.scopes:
            raise HTTPException(
                status_code=403,
                detail=f"API key lacks '{scope}' scope",
            )
        return key
    return checker
