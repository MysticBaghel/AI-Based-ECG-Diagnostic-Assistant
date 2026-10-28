"""Add versioned analysis results and remove the doctor assignment cache.

The old ``known_sessions.doctor_ids`` column existed only so viewer access could
be computed from doctor-patient assignments. That model is gone; access is now
"any authenticated operator". The column is dropped rather than left unused so
the schema matches the code.

SQLite has no ``ALTER TABLE ... DROP COLUMN`` in older versions, so Alembic's
batch mode recreates the table on SQLite and uses a plain drop on PostgreSQL.

Revision ID: 0002_analysis
Revises: 0001_telemetry
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002_analysis"
down_revision: Union[str, None] = "0001_telemetry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("known_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column(
            "analysis",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "analyzed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "session_id", "version", name="uq_analysis_session_version"
        ),
    )
    op.create_index(
        "ix_analysis_session_analyzed",
        "analysis_results",
        ["session_id", "analyzed_at"],
    )

    with op.batch_alter_table("known_sessions") as batch:
        batch.drop_column("doctor_ids")


def downgrade() -> None:
    with op.batch_alter_table("known_sessions") as batch:
        batch.add_column(
            sa.Column(
                "doctor_ids",
                sa.JSON().with_variant(JSONB(), "postgresql"),
                nullable=False,
                server_default="[]",
            )
        )

    op.drop_index("ix_analysis_session_analyzed", table_name="analysis_results")
    op.drop_table("analysis_results")
