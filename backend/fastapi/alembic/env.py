"""Alembic environment.

The URL and the schema both come from `app.core.config`, so `alembic upgrade
head` always targets exactly what the application uses - including the SQLite
test configuration, which is how the test suite checks that the migrations and
the models agree.

`version_table_schema` is decided in `run_migrations_online`: on PostgreSQL the
`version_table_schema` argument makes Alembic create the `telemetry` schema
itself if it is missing, so the very first migration does not have to.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importing the models registers every table on Base.metadata, which is what
# autogenerate and the consistency test compare against.
from app.db import Base  # noqa: E402
from app import models  # noqa: E402,F401

target_metadata = Base.metadata

SCHEMA = settings.telemetry_schema_name
VERSION_TABLE = "alembic_version"


def _database_url() -> str:
    """The application URL, forced to a synchronous driver.

    Alembic runs migrations synchronously; psycopg3 exposes both, and SQLite is
    synchronous under the `sqlite+aiosqlite` URL, so the driver name is swapped.
    """
    url = settings.database_url
    return (
        url.replace("+psycopg_async", "+psycopg")
        .replace("+aiosqlite", "")
        .replace("+asyncpg", "+psycopg")
    )


def _version_table_schema() -> str | None:
    if SCHEMA and not _database_url().startswith("sqlite"):
        return SCHEMA
    return None


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: emit SQL instead of running it."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=bool(SCHEMA),
        version_table_schema=_version_table_schema(),
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=bool(SCHEMA),
            # Passing the schema here is what makes Alembic create it before it
            # tries to create its own version table inside it.
            version_table_schema=_version_table_schema(),
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
