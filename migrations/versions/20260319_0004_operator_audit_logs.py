"""Add operator audit logs.

Revision ID: 20260319_0004
Revises: 20260319_0003
Create Date: 2026-03-19 17:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0004"
down_revision = "20260319_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operator_audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=48), nullable=False),
        sa.Column("target_type", sa.String(length=48), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("operator_id", sa.String(length=120), nullable=True),
        sa.Column("region_id", sa.String(length=32), nullable=True),
        sa.Column("week_start_date", sa.Date(), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_operator_audit_logs_action_type", "operator_audit_logs", ["action_type"], unique=False)
    op.create_index("ix_operator_audit_logs_target_type", "operator_audit_logs", ["target_type"], unique=False)
    op.create_index("ix_operator_audit_logs_target_id", "operator_audit_logs", ["target_id"], unique=False)
    op.create_index("ix_operator_audit_logs_operator_id", "operator_audit_logs", ["operator_id"], unique=False)
    op.create_index("ix_operator_audit_logs_region_id", "operator_audit_logs", ["region_id"], unique=False)
    op.create_index("ix_operator_audit_logs_week_start_date", "operator_audit_logs", ["week_start_date"], unique=False)
    op.create_index("ix_operator_audit_logs_model_version", "operator_audit_logs", ["model_version"], unique=False)
    op.create_index("ix_operator_audit_logs_created_at", "operator_audit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_operator_audit_logs_created_at", table_name="operator_audit_logs")
    op.drop_index("ix_operator_audit_logs_model_version", table_name="operator_audit_logs")
    op.drop_index("ix_operator_audit_logs_week_start_date", table_name="operator_audit_logs")
    op.drop_index("ix_operator_audit_logs_region_id", table_name="operator_audit_logs")
    op.drop_index("ix_operator_audit_logs_operator_id", table_name="operator_audit_logs")
    op.drop_index("ix_operator_audit_logs_target_id", table_name="operator_audit_logs")
    op.drop_index("ix_operator_audit_logs_target_type", table_name="operator_audit_logs")
    op.drop_index("ix_operator_audit_logs_action_type", table_name="operator_audit_logs")
    op.drop_table("operator_audit_logs")
