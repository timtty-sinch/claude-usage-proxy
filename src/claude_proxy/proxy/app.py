"""FastAPI application factory with lifespan."""

import truststore
truststore.inject_into_ssl()

from contextlib import asynccontextmanager

from fastapi import FastAPI

from claude_proxy.db.engine import async_engine, configure_async_db
from claude_proxy.db.models import Base
from claude_proxy.proxy.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables if they don't exist (Alembic handles migrations in production)
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await configure_async_db()
    yield
    await async_engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Claude Usage Proxy",
        description="Local HTTP proxy for Claude API usage tracking",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app
