"""Create preventive-inspection PostgreSQL tables.

Revision ID: 0001_postgres_api
Revises:
Create Date: 2026-08-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_postgres_api"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "tractors",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("model_name", sa.String(length=32), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("model_name = 'Fendt 314'", name="ck_tractors_model_name"),
        sa.ForeignKeyConstraint(["fleet_id"], ["fleets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fleet_id", "external_id", name="uq_tractors_fleet_external_id"),
    )
    op.create_table(
        "scored_windows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tractor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_version", sa.String(length=32), nullable=False),
        sa.Column("mission_index", sa.Integer(), nullable=False),
        sa.Column("window_index", sa.Integer(), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("span_seconds", sa.Float(), nullable=False),
        sa.Column("window_quality", sa.String(length=32), nullable=False),
        sa.Column("model_features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("physical_durations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("dataset_split", sa.String(length=16), nullable=True),
        sa.Column("source_reference", sa.String(length=512), nullable=False),
        sa.Column("evidence_role", sa.String(length=32), nullable=False),
        sa.Column("operational_regime", sa.Integer(), nullable=False),
        sa.Column("contextual_rarity_score", sa.Float(), nullable=False),
        sa.Column("contextual_rarity_threshold", sa.Float(), nullable=False),
        sa.Column("physical_eligible", sa.Boolean(), nullable=False),
        sa.Column("physical_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("hybrid_alert", sa.Boolean(), nullable=False),
        sa.Column("contextual_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("model_version = 'fendt314-hybrid-v2.0.1'", name="ck_scored_windows_model_version"),
        sa.CheckConstraint(
            "mission_index >= 0 AND window_index >= 0",
            name="ck_scored_windows_non_negative_identity",
        ),
        sa.CheckConstraint(
            "evidence_role = 'operational_output_only'",
            name="ck_scored_windows_evidence_role",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(model_features) = 'object' "
            "AND jsonb_typeof(physical_durations) = 'object' "
            "AND jsonb_typeof(physical_reasons) = 'array' "
            "AND jsonb_typeof(contextual_reasons) = 'array'",
            name="ck_scored_windows_json_shapes",
        ),
        sa.CheckConstraint(
            "(window_quality = 'partial_coverage' AND sample_count BETWEEN 55 AND 59 "
            "AND span_seconds >= 54.0 AND span_seconds <= 60.000001) OR "
            "(window_quality = 'complete' AND sample_count = 60 "
            "AND span_seconds >= 54.0 AND span_seconds <= 60.000001) OR "
            "(window_quality = 'boundary_jitter' AND sample_count = 61 "
            "AND span_seconds >= 59.0 AND span_seconds <= 60.000001)",
            name="ck_scored_windows_complete_window",
        ),
        sa.CheckConstraint(
            "source_kind IN ('observed_dataset_replay', 'synthetic_demo', 'live_observed') "
            "AND ((source_kind = 'observed_dataset_replay' AND dataset_split IN ('train', 'validation')) "
            "OR (source_kind IN ('synthetic_demo', 'live_observed') AND dataset_split IS NULL))",
            name="ck_scored_windows_provenance",
        ),
        sa.ForeignKeyConstraint(["tractor_id"], ["tractors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_scored_windows_idempotency_key"),
        sa.UniqueConstraint(
            "model_version",
            "tractor_id",
            "mission_index",
            "window_index",
            "observed_at_utc",
            name="uq_scored_windows_identity",
        ),
    )
    op.create_index(
        "ix_scored_windows_tractor_observed_id",
        "scored_windows",
        ["tractor_id", "observed_at_utc", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_scored_windows_tractor_observed_id", table_name="scored_windows")
    op.drop_table("scored_windows")
    op.drop_table("tractors")
    op.drop_table("fleets")
