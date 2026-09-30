"""
SQLAlchemy async engine and session factory.

Usage:
    from src.api.database import get_session
    async with get_session() as session:
        result = await session.execute(...)
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from . import config as api_config

# aiosqlite connections bind to the event loop that created them. Pooled
# connections raise "attached to a different loop" when reused across loops
# (e.g. FastAPI TestClient portals, or multiple asyncio.run calls). SQLite's
# connect cost is trivial, so sqlite URLs run pool-free; server databases
# keep the default pool.
_ENGINE_KWARGS = {"poolclass": NullPool} if api_config.DATABASE_URL.startswith("sqlite") else {}

engine = create_async_engine(
    api_config.DATABASE_URL,
    echo=api_config.DEBUG,
    future=True,
    **_ENGINE_KWARGS,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    """Yield an async session (for FastAPI dependency injection)."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def run_best_effort_migrations(engine) -> None:
    """Apply idempotent, best-effort schema migrations for existing databases.

    `Base.metadata.create_all` creates missing tables but never alters
    existing ones, so a local DB created before a column was added would
    keep working but silently drop the new field. Each migration is one
    ALTER wrapped in try/except: on SQLite/Postgres a duplicate-column
    error means the column already exists, which is success for our
    purposes. Anything else (locked DB, permissions) is swallowed too —
    this must never block startup.
    """
    migrations = (
        # 2026-09: provenance column added to spill incidents
        "ALTER TABLE spill_incidents ADD COLUMN data_source VARCHAR(50)",
    )
    for statement in migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(statement))
        except Exception:
            pass


async def init_db():
    """Create all tables, then apply best-effort migrations. Safe on every startup."""
    from .models.spill import SpillIncident  # noqa
    from .models.flare import GasFlare  # noqa
    from .models.disclosure import Disclosure  # noqa

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_best_effort_migrations(engine)
