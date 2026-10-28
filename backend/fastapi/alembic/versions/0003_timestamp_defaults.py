"""Use a portable CURRENT_TIMESTAMP default on every timestamp column.

Migration 0001 used ``sa.func.now()`` for the server defaults. On SQLite that
rendered ``DEFAULT (now())``, and SQLite has no ``now()`` function, so the first
insert that relied on the default failed at runtime. The schema was never
exercised through Alembic in the original suite (tests create tables from the
models), which is how the bug survived.

``CURRENT_TIMESTAMP`` is valid on both SQLite and PostgreSQL. This migration
rebuilds the affected tables in place (Alembic batch mode on SQLite) and keeps
all existing rows.

Revision ID: 0003_timestamp_defaults
Revises: 0002_analysis
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_timestamp_defaults"
down_revision: Union[str, None] = "0002_analysis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = {
    "known_sessions": ["registered_at", "updated_at"],
    "device_connections": ["created_at"],
    "sensor_readings": ["received_at"],
    "ecg_chunks": ["received_at"],
    "analysis_results": ["analyzed_at"],
    "revoked_devices": ["revoked_at"],
}


def upgrade() -> None:
    for table, columns in _TABLES.items():
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.alter_column(
                    column,
                    existing_type=sa.DateTime(timezone=True),
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                    existing_nullable=False,
                )


def downgrade() -> None:
    for table, columns in _TABLES.items():
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.alter_column(
                    column,
                    existing_type=sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    existing_nullable=False,
                )
