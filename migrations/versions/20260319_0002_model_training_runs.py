"""Add model training run registry.

Revision ID: 20260319_0002
Revises: 20260319_0001
Create Date: 2026-03-19 13:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0002"
down_revision = "20260319_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_training_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("model_family", sa.String(length=64), nullable=False),
        sa.Column("registry_status", sa.String(length=24), nullable=False),
        sa.Column("promotion_status", sa.String(length=24), nullable=False),
        sa.Column("feature_build_version", sa.String(length=50), nullable=True),
        sa.Column("artifact_path", sa.Text(), nullable=False),
        sa.Column("metadata_path", sa.Text(), nullable=False),
        sa.Column("model_card_path", sa.Text(), nullable=True),
        sa.Column("training_rows", sa.Integer(), nullable=False),
        sa.Column("training_weeks", sa.Integer(), nullable=False),
        sa.Column("evaluation_splits", sa.Integer(), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("model_version"),
    )
    op.create_index("ix_model_training_runs_model_version", "model_training_runs", ["model_version"], unique=False)
    op.create_index("ix_model_training_runs_registry_status", "model_training_runs", ["registry_status"], unique=False)
    op.create_index("ix_model_training_runs_trained_at", "model_training_runs", ["trained_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_model_training_runs_trained_at", table_name="model_training_runs")
    op.drop_index("ix_model_training_runs_registry_status", table_name="model_training_runs")
    op.drop_index("ix_model_training_runs_model_version", table_name="model_training_runs")
    op.drop_table("model_training_runs")
