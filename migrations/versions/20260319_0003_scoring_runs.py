"""Add scoring run registry.

Revision ID: 20260319_0003
Revises: 20260319_0002
Create Date: 2026-03-19 14:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0003"
down_revision = "20260319_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scoring_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_scope", sa.String(length=24), nullable=False),
        sa.Column("run_status", sa.String(length=24), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("feature_build_version", sa.String(length=50), nullable=True),
        sa.Column("latest_week_start_date", sa.Date(), nullable=True),
        sa.Column("weeks_scored", sa.Integer(), nullable=False),
        sa.Column("rows_scored", sa.Integer(), nullable=False),
        sa.Column("rows_inserted", sa.Integer(), nullable=False),
        sa.Column("rows_updated", sa.Integer(), nullable=False),
        sa.Column("alerts_created_or_updated", sa.Integer(), nullable=False),
        sa.Column("alerts_removed", sa.Integer(), nullable=False),
        sa.Column("medium_or_higher_alerts", sa.Integer(), nullable=False),
        sa.Column("high_alerts", sa.Integer(), nullable=False),
        sa.Column("medium_or_higher_alert_rate", sa.Float(), nullable=True),
        sa.Column("high_alert_rate", sa.Float(), nullable=True),
        sa.Column("average_score", sa.Float(), nullable=True),
        sa.Column("max_score", sa.Float(), nullable=True),
        sa.Column("non_ok_quality_rows", sa.Integer(), nullable=False),
        sa.Column("feature_freshness", sa.JSON(), nullable=False),
        sa.Column("feature_drift", sa.JSON(), nullable=False),
        sa.Column("alert_volume", sa.JSON(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scoring_runs_run_scope", "scoring_runs", ["run_scope"], unique=False)
    op.create_index("ix_scoring_runs_run_status", "scoring_runs", ["run_status"], unique=False)
    op.create_index("ix_scoring_runs_model_version", "scoring_runs", ["model_version"], unique=False)
    op.create_index("ix_scoring_runs_latest_week_start_date", "scoring_runs", ["latest_week_start_date"], unique=False)
    op.create_index("ix_scoring_runs_executed_at", "scoring_runs", ["executed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scoring_runs_executed_at", table_name="scoring_runs")
    op.drop_index("ix_scoring_runs_latest_week_start_date", table_name="scoring_runs")
    op.drop_index("ix_scoring_runs_model_version", table_name="scoring_runs")
    op.drop_index("ix_scoring_runs_run_status", table_name="scoring_runs")
    op.drop_index("ix_scoring_runs_run_scope", table_name="scoring_runs")
    op.drop_table("scoring_runs")
