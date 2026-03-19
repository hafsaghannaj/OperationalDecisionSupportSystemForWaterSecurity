"""Create initial AquaIntel schema.

Revision ID: 20260319_0001
Revises:
Create Date: 2026-03-19 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "source_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_name", sa.String(length=120), nullable=False),
        sa.Column("upstream_asset_uri", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=255), nullable=True),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_runs_source_name", "source_runs", ["source_name"], unique=False)

    op.create_table(
        "admin_boundaries",
        sa.Column("region_id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country_code", sa.String(length=8), nullable=False),
        sa.Column("admin_level", sa.Integer(), nullable=False),
        sa.Column("source_run_id", sa.String(length=36), nullable=True),
        sa.Column("geom", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["source_run_id"], ["source_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("region_id"),
    )
    op.execute(
        """
        ALTER TABLE admin_boundaries
        ALTER COLUMN geom TYPE geometry(MULTIPOLYGON, 4326)
        USING CASE
            WHEN geom IS NULL THEN NULL
            ELSE ST_GeomFromText(geom, 4326)
        END
        """
    )
    op.create_index("ix_admin_boundaries_country_code", "admin_boundaries", ["country_code"], unique=False)
    op.create_index("ix_admin_boundaries_geom", "admin_boundaries", ["geom"], unique=False, postgresql_using="gist")

    op.create_table(
        "district_week_features",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("region_id", sa.String(length=32), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("country_code", sa.String(length=8), nullable=False),
        sa.Column("admin_level", sa.Integer(), nullable=False),
        sa.Column("source_run_id", sa.String(length=36), nullable=True),
        sa.Column("feature_build_version", sa.String(length=50), nullable=False),
        sa.Column("quality_flag", sa.String(length=32), nullable=False),
        sa.Column("rainfall_total_mm_7d", sa.Float(), nullable=True),
        sa.Column("rainfall_anomaly_zscore", sa.Float(), nullable=True),
        sa.Column("population_total", sa.Float(), nullable=True),
        sa.Column("population_density_km2", sa.Float(), nullable=True),
        sa.Column("wash_access_basic_water_pct", sa.Float(), nullable=True),
        sa.Column("wash_access_basic_sanitation_pct", sa.Float(), nullable=True),
        sa.Column("lag_case_count_1w", sa.Integer(), nullable=True),
        sa.Column("rolling_case_count_4w", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["region_id"], ["admin_boundaries.region_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_run_id"], ["source_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_id", "week_start_date", "feature_build_version", name="uq_features_region_week_build"),
    )
    op.create_index(
        "ix_district_week_features_region_week",
        "district_week_features",
        ["region_id", "week_start_date"],
        unique=False,
    )

    op.create_table(
        "district_week_labels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("region_id", sa.String(length=32), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("label_event", sa.Boolean(), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=True),
        sa.Column("label_source", sa.String(length=120), nullable=False),
        sa.Column("label_observed_at", sa.Date(), nullable=True),
        sa.Column("source_run_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["region_id"], ["admin_boundaries.region_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_run_id"], ["source_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_id", "week_start_date", "label_source", name="uq_labels_region_week_source"),
    )
    op.create_index(
        "ix_district_week_labels_region_week",
        "district_week_labels",
        ["region_id", "week_start_date"],
        unique=False,
    )

    op.create_table(
        "risk_scores",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("region_id", sa.String(length=32), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("driver_contributions", sa.JSON(), nullable=False),
        sa.Column("driver_narrative", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["region_id"], ["admin_boundaries.region_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_id", "week_start_date", name="uq_risk_scores_region_week"),
    )
    op.create_index("ix_risk_scores_week_start_date", "risk_scores", ["week_start_date"], unique=False)

    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("region_id", sa.String(length=32), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["region_id"], ["admin_boundaries.region_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("region_id", "week_start_date", name="uq_alert_events_region_week"),
    )
    op.create_index("ix_alert_events_region_week", "alert_events", ["region_id", "week_start_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_alert_events_region_week", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_index("ix_risk_scores_week_start_date", table_name="risk_scores")
    op.drop_table("risk_scores")
    op.drop_index("ix_district_week_labels_region_week", table_name="district_week_labels")
    op.drop_table("district_week_labels")
    op.drop_index("ix_district_week_features_region_week", table_name="district_week_features")
    op.drop_table("district_week_features")
    op.drop_index("ix_admin_boundaries_geom", table_name="admin_boundaries")
    op.drop_index("ix_admin_boundaries_country_code", table_name="admin_boundaries")
    op.drop_table("admin_boundaries")
    op.drop_index("ix_source_runs_source_name", table_name="source_runs")
    op.drop_table("source_runs")
