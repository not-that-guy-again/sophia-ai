import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sophia.api.audit_routes import router as audit_router
from sophia.api.routes import router
from sophia.api.webhook_routes import webhook_router
from sophia.audit.database import close_db, init_db
from sophia.config import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(settings)
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
