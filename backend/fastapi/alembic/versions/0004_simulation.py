"""Add `simulation_runs` - provenance for the built-in simulator.

The dashboard can stream a chosen scenario into an active session without a
physical device. The samples are stored through the normal ingestion path, so
the recording is indistinguishable from a real one in every downstream table -
which is exactly why the run itself has to be recorded. The analysis copies the
scenario into its stored payload, so a report can say "demonstration data" and
never presents a simulated rhythm as a patient recording.

Revision ID: 0004_simulation
Revises: 0003_timestamp_defaults
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_simulation"
down_revision: Union[str, None] = "0003_timestamp_defaults"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("known_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scenario", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chunks_sent", sa.Integer(), nullable=False),
        sa.Column("readings_sent", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
    )
    op.create_index(
        "ix_simulation_session_started",
        "simulation_runs",
        ["session_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_simulation_session_started", table_name="simulation_runs")
    op.drop_table("simulation_runs")
