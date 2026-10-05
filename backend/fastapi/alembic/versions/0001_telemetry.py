"""Create the telemetry tables.

Revision ID: 0001_telemetry
Revises:
Create Date: 2026-10-05

The schema itself is created by Alembic: `version_table_schema` in
alembic/env.py makes it create `telemetry` before it creates its own version
table there, so this migration can go straight to the tables.

`op.create_table` without a `schema=` argument uses the metadata schema from
`app.db.Base`, which is `telemetry` on PostgreSQL and None on SQLite - the same
switch the application uses, so the test suite exercises these migrations on
SQLite.

`id`/`session_id`/`device_id` primary keys have no server default: the
application generates UUIDs (`default=uuid.uuid4`), and the SQLite dialect
cannot add a column with a volatile server default. The model and the migration
therefore agree, which is what the consistency test checks.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0001_telemetry"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "known_sessions",
        sa.Column("session_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("patient_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "doctor_ids",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "device_connections",
        sa.Column("device_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("firmware_version", sa.String(length=50), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_table(
        "sensor_readings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("known_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("sensor_type", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "session_id",
            "sensor_type",
            "recorded_at",
            name="uq_reading_session_type_time",
        ),
    )
    op.create_index(
        "ix_reading_session_time",
        "sensor_readings",
        ["session_id", "recorded_at"],
    )

    op.create_table(
        "ecg_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("known_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_rate_hz", sa.Integer(), nullable=False),
        sa.Column(
            "samples",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "session_id", "chunk_index", name="uq_ecg_session_chunk"
        ),
    )
    op.create_index(
        "ix_ecg_session_start", "ecg_chunks", ["session_id", "start_time"]
    )

    op.create_table(
        "revoked_devices",
        sa.Column("device_id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_ecg_session_start", table_name="ecg_chunks")
    op.drop_table("ecg_chunks")
    op.drop_index("ix_reading_session_time", table_name="sensor_readings")
    op.drop_table("sensor_readings")
    op.drop_table("revoked_devices")
    op.drop_table("device_connections")
    op.drop_table("known_sessions")
