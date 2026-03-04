from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from claude_proxy.config import settings


def _async_db_url() -> str:
    return f"sqlite+aiosqlite:///{settings.db_path}"


def _sync_db_url() -> str:
    return f"sqlite:///{settings.db_path}"


# Async engine for FastAPI proxy routes
async_engine = create_async_engine(_async_db_url(), echo=False)
AsyncSessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def configure_async_db() -> None:
    """Run once at startup to set SQLite pragmas."""
    async with async_engine.connect() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=10000"))
        await conn.commit()


# Sync engine for CLI/TUI (no event loop needed)
sync_engine = create_engine(_sync_db_url(), echo=False)
SyncSessionLocal = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


@event.listens_for(sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA busy_timeout=10000")


async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_session() -> Session:
    with SyncSessionLocal() as session:
        yield session
