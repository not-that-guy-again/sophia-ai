"""Async database engine and session management for the audit system."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sophia.audit.models import Base
from sophia.config import Settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


async def init_db(settings: Settings | None = None) -> None:
    """Initialize the async database engine and create tables."""
    global _engine, _session_factory

    if settings is None:
        settings = Settings()

    _engine = create_async_engine(settings.database_url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Audit database initialized: %s", settings.database_url)


async def close_db() -> None:
    """Close the database engine."""
    global _engine, _session_factory

    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Audit database connection closed")


def get_session() -> AsyncSession:
    """Get a new async database session."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _session_factory()
