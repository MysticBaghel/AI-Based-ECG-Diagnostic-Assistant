"""The Alembic migrations and the SQLAlchemy models must describe one schema.

`alembic upgrade head` is run in a subprocess against a throwaway SQLite file
(SQLite is what the suite can run on here; the migration body is
dialect-independent because the schema is applied by `app.db`), and the result is
compared with `Base.metadata`. If a model gains a column and no migration
mentions it, this test fails - which is the whole point.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from app.db import Base
from app import models  # noqa: F401  (registers the tables)

FASTAPI_DIR = Path(__file__).resolve().parent.parent


def _run_alembic(database_url: str) -> subprocess.CompletedProcess:
    """Upgrade to head, with stdout/stderr in files.

    `capture_output=True` opens anonymous pipes, which the confined Windows
    sandbox of this workspace denies; files work everywhere.
    """
    workdir = FASTAPI_DIR / "tests_tmp"
    workdir.mkdir(exist_ok=True)
    stdout_path = workdir / "alembic_stdout.txt"
    stderr_path = workdir / "alembic_stderr.txt"

    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    env["TELEMETRY_SCHEMA"] = ""
    env["JWT_SIGNING_KEY"] = env.get("JWT_SIGNING_KEY", "test-only-jwt-signing-key")

    with open(stdout_path, "w", encoding="utf-8") as stdout_file, open(
        stderr_path, "w", encoding="utf-8"
    ) as stderr_file:
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=FASTAPI_DIR,
            env=env,
            stdout=stdout_file,
            stderr=stderr_file,
            timeout=180,
        )

    completed.stdout_text = stdout_path.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    completed.stderr_text = stderr_path.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    return completed


@pytest.fixture(scope="module")
def migrated_database(tmp_path_factory):
    database_path = tmp_path_factory.mktemp("migrations") / "migrated.sqlite3"
    result = _run_alembic(f"sqlite:///{database_path.as_posix()}")

    assert result.returncode == 0, result.stderr_text

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    yield engine
    engine.dispose()


def test_migrations_create_every_table_the_models_declare(migrated_database):
    migrated = set(inspect(migrated_database).get_table_names())
    declared = set(Base.metadata.tables)

    assert declared - migrated == set(), "models have tables with no migration"


def test_migrations_do_not_create_tables_the_models_do_not_declare(migrated_database):
    migrated = set(inspect(migrated_database).get_table_names()) - {"alembic_version"}
    declared = set(Base.metadata.tables)

    assert migrated - declared == set(), "migration creates an unknown table"


def test_every_column_matches_between_migration_and_models(migrated_database):
    inspector = inspect(migrated_database)

    for table_name, table in Base.metadata.tables.items():
        migrated_columns = {column["name"] for column in inspector.get_columns(table_name)}
        declared_columns = set(table.columns.keys())

        assert migrated_columns == declared_columns, f"column mismatch on {table_name}"


def test_unique_constraints_match(migrated_database):
    """The two idempotency rules must exist in the migrated schema too."""
    inspector = inspect(migrated_database)

    reading_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("sensor_readings")
    }
    chunk_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("ecg_chunks")
    }

    assert ("session_id", "sensor_type", "recorded_at") in reading_constraints
    assert ("session_id", "chunk_index") in chunk_constraints


def test_migrations_can_be_rolled_back(tmp_path):
    """`downgrade base` on the same file leaves no telemetry tables behind."""
    database_path = tmp_path / "rollback.sqlite3"
    url = f"sqlite:///{database_path.as_posix()}"

    assert _run_alembic(url).returncode == 0

    env = dict(os.environ)
    env["DATABASE_URL"] = url
    env["TELEMETRY_SCHEMA"] = ""
    env["JWT_SIGNING_KEY"] = env.get("JWT_SIGNING_KEY", "test-only-jwt-signing-key")

    workdir = FASTAPI_DIR / "tests_tmp"
    workdir.mkdir(exist_ok=True)
    with open(workdir / "downgrade.txt", "w", encoding="utf-8") as output:
        downgrade = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "base"],
            cwd=FASTAPI_DIR,
            env=env,
            stdout=output,
            stderr=output,
            timeout=180,
        )

    assert downgrade.returncode == 0

    engine = create_engine(url)
    remaining = set(inspect(engine).get_table_names())
    engine.dispose()

    assert remaining - {"alembic_version"} == set()
