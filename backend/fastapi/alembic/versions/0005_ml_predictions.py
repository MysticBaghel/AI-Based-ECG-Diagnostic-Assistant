"""Add `ml_predictions` - queryable storage for each analysis run's ML output.

`analysis_results.analysis` already stores the full JSON payload. This table is
the projection the application can query and audit: model identity, predicted
class, confidence, signal quality, heart rate and the advisory outcome, with the
complete ML/advisory snapshots alongside. One row per analysis version; the
unique `analysis_result_id` makes a retry of the same version idempotent.

Revision ID: 0005_ml_predictions
Revises: 0004_simulation
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005_ml_predictions"
down_revision: Union[str, None] = "0004_simulation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ml_predictions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("known_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "analysis_result_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("analysis_results.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("analysis_version", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("model_version", sa.String(length=100), nullable=True),
        sa.Column("model_sha256", sa.String(length=64), nullable=True),
        sa.Column("predicted_class", sa.String(length=8), nullable=True),
        sa.Column("predicted_label", sa.String(length=80), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("heart_rate_bpm", sa.Float(), nullable=True),
        sa.Column("window_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signal_duration_seconds", sa.Float(), nullable=True),
        sa.Column("advisor_provider", sa.String(length=40), nullable=True),
        sa.Column("advice_risk_level", sa.String(length=20), nullable=True),
        sa.Column(
            "ml",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "advice",
            sa.JSON().with_variant(JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "analysis_result_id",
            name="uq_ml_prediction_analysis",
        ),
    )
    op.create_index(
        "ix_ml_prediction_session_created",
        "ml_predictions",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ml_prediction_session_created", table_name="ml_predictions")
    op.drop_table("ml_predictions")
