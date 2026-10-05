"""Async SQLAlchemy engine, session factory and declarative base.

One schema, ``telemetry``, holds every table in this service. ``metadata.schema``
is set before the models are imported, so every table lands in it without each
model repeating itself - and setting ``TELEMETRY_SCHEMA=""`` turns it off for
SQLite, which has no schemas.
"""

from collections.abc import AsyncIterator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import TELEMETRY_SCHEMA, settings

# The test suite points DATABASE_URL at SQLite. `check_same_thread` is a SQLite
# driver argument and must not reach psycopg.
_IS_SQLITE = settings.database_url.startswith("sqlite")

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _IS_SQLITE else {},
)

SessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    # SQLite serialises writers; letting the session autoflush turns a read into
    # a surprise write that can block. The endpoints commit explicitly anyway.
    autoflush=not _IS_SQLITE,
)


class Base(DeclarativeBase):
    metadata = MetaData(schema=TELEMETRY_SCHEMA)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, always closed."""
    async with SessionFactory() as session:
        yield session


async def create_all() -> None:
    """Create missing tables.

    Convenient for a first run and for the SQLite test database. PostgreSQL in
    production is owned by Alembic, which creates the schema first
    (``alembic upgrade head``); this call is then a no-op.
    """
    from app import models  # noqa: F401  (import registers the tables)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
