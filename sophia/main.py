import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sophia.api.admin_routes import admin_router
from sophia.api.audit_routes import router as audit_router
from sophia.api.routes import router
from sophia.api.webhook_routes import webhook_router
from sophia.audit.database import close_db, init_db
from sophia.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def _bootstrap_auth() -> None:
    """Generate bootstrap admin key if auth is enabled and no keys exist."""
    if not settings.auth_enabled:
        return

    from sqlalchemy import func, select

    from sophia.auth.keys import generate_key
    from sophia.auth.models import APIKeyRecord
    from sophia.audit.database import get_session

    async with get_session() as session:
        result = await session.execute(select(func.count()).select_from(APIKeyRecord))
        count = result.scalar()
        if count == 0:
            full_key, record = generate_key(
                tenant_id="bootstrap",
                hat_name="customer-service",
                scopes=["admin", "chat"],
            )
            session.add(record)
            await session.commit()
            logger.info("=" * 60)
            logger.info("BOOTSTRAP API KEY (save this — shown only once):")
            logger.info("  %s", full_key)
            logger.info("=" * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(settings)
    await _bootstrap_auth()
    yield
    await close_db()


app = FastAPI(
    title="Sophia",
    description="Consequence-Aware AI Agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(audit_router)
app.include_router(webhook_router)
app.include_router(admin_router)
