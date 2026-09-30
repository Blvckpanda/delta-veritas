"""
SQLAlchemy async engine and session factory.

Usage:
    from src.api.database import get_session
    async with get_session() as session:
        result = await session.execute(...)
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from . import config as api_config

engine = create_async_engine(
    api_config.DATABASE_URL,
    echo=api_config.DEBUG,
    future=True,
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


async def init_db():
    """Create all tables. Safe to call on every startup (CREATE IF NOT EXISTS)."""
    from .models.spill import SpillIncident  # noqa
    from .models.flare import GasFlare  # noqa
    from .models.disclosure import Disclosure  # noqa

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
