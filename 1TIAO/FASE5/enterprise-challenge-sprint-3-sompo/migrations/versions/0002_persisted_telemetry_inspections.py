"""Persist observed telemetry imports and immutable inspection cases.

Revision ID: 0002_telemetry_inspections
Revises: 0001_postgres_api
Create Date: 2026-08-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_telemetry_inspections"
down_revision = "0001_postgres_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telemetry_imports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tractor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_split", sa.String(length=16), nullable=False),
        sa.Column("source_format", sa.String(length=32), nullable=False),
        sa.Column("source_file_name", sa.String(length=255), nullable=False),
        sa.Column("source_member", sa.String(length=512), nullable=True),
        sa.Column("source_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("semantic_sha256", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("transform_version", sa.String(length=64), nullable=False),
        sa.Column("epoch_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.BigInteger(), nullable=False),
        sa.Column("mission_count", sa.Integer(), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("dataset_split IN ('train', 'validation')", name="ck_telemetry_imports_split"),
        sa.CheckConstraint(
            "source_format IN ('canonical_csv', 'canonical_csv_gz', 'fendt314_zip')",
            name="ck_telemetry_imports_source_format",
        ),
        sa.CheckConstraint(
            "(source_format = 'fendt314_zip' AND source_member IS NOT NULL) OR "
            "(source_format IN ('canonical_csv', 'canonical_csv_gz') AND source_member IS NULL)",
            name="ck_telemetry_imports_source_member",
        ),
        sa.CheckConstraint("source_size_bytes > 0", name="ck_telemetry_imports_source_size"),
        sa.CheckConstraint("sample_count > 0 AND mission_count > 0", name="ck_telemetry_imports_counts"),
        sa.CheckConstraint("schema_version = 'fendt314-telemetry-v1'", name="ck_telemetry_imports_schema"),
        sa.CheckConstraint(
            "epoch_utc = TIMESTAMPTZ '2024-04-26 13:22:25.100+00'",
            name="ck_telemetry_imports_epoch",
        ),
        sa.CheckConstraint(
            "transform_version IN ('canonical-pass-through-v1', 'fendt314-original-to-1hz-v1')",
            name="ck_telemetry_imports_transform",
        ),
        sa.CheckConstraint("ended_at_utc >= started_at_utc", name="ck_telemetry_imports_interval"),
        sa.ForeignKeyConstraint(["tractor_id"], ["tractors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tractor_id", "dataset_split", "source_sha256", "transform_version", name="uq_telemetry_imports_source"),
        sa.UniqueConstraint("semantic_sha256", name="uq_telemetry_imports_semantic"),
    )
    op.create_index("ix_telemetry_imports_tractor_interval", "telemetry_imports", ["tractor_id", "started_at_utc", "ended_at_utc"], unique=False)

    op.create_table(
        "telemetry_missions",
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mission_index", sa.Integer(), nullable=False),
        sa.Column("origin_position_deciseconds", sa.BigInteger(), nullable=False),
        sa.Column("first_position_deciseconds", sa.BigInteger(), nullable=False),
        sa.Column("last_position_deciseconds", sa.BigInteger(), nullable=False),
        sa.Column("first_source_row", sa.BigInteger(), nullable=False),
        sa.Column("last_source_row", sa.BigInteger(), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("mission_index >= 0 AND origin_position_deciseconds >= 0", name="ck_telemetry_missions_non_negative"),
        sa.CheckConstraint("first_position_deciseconds >= origin_position_deciseconds AND last_position_deciseconds >= first_position_deciseconds", name="ck_telemetry_missions_positions"),
        sa.CheckConstraint("first_source_row >= 0 AND last_source_row >= first_source_row", name="ck_telemetry_missions_source_rows"),
        sa.CheckConstraint("sample_count > 0 AND ended_at_utc >= started_at_utc", name="ck_telemetry_missions_interval"),
        sa.ForeignKeyConstraint(["import_id"], ["telemetry_imports.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("import_id", "mission_index"),
    )

    op.create_table(
        "telemetry_samples",
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mission_index", sa.Integer(), nullable=False),
        sa.Column("position_deciseconds", sa.BigInteger(), nullable=False),
        sa.Column("source_row", sa.BigInteger(), nullable=False),
        sa.Column("observed_at_utc", sa.DateTime(timezone=True), nullable=False),
        *(sa.Column(field, sa.Float(), nullable=True) for field in (
            "engine_rpm", "actual_engine_torque_pct", "engine_load_pct", "accelerator_pct",
            "coolant_temp_c", "front_axle_speed_kph", "speed_over_ground_mps",
            "ground_implement_speed_mmps", "wheel_vehicle_speed_kph", "rear_pto_rpm",
            "rear_hitch_position", "rear_hitch_in_work", "rear_link_force_pct", "rear_draft_n",
            "ground_machine_speed_mps", "machine_selected_speed_mps", "wheel_machine_speed_mps",
        )),
        sa.CheckConstraint("mission_index >= 0 AND position_deciseconds >= 0 AND source_row >= 0", name="ck_telemetry_samples_non_negative"),
        sa.ForeignKeyConstraint(["import_id", "mission_index"], ["telemetry_missions.import_id", "telemetry_missions.mission_index"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("import_id", "mission_index", "position_deciseconds"),
        sa.UniqueConstraint("import_id", "source_row", name="uq_telemetry_samples_source_row"),
    )
    op.create_index("ix_telemetry_samples_import_observed", "telemetry_samples", ["import_id", "observed_at_utc"], unique=False)

    op.add_column("scored_windows", sa.Column("telemetry_import_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_scored_windows_telemetry_import", "scored_windows", "telemetry_imports", ["telemetry_import_id"], ["id"], ondelete="RESTRICT")
    op.create_index("ix_scored_windows_telemetry_import", "scored_windows", ["telemetry_import_id"], unique=False)

    op.create_table(
        "inspection_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tractor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("assignee", sa.String(length=120), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("evidence_as_of_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_schema_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_sha256", sa.String(length=64), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=True),
        sa.Column("result_notes", sa.Text(), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')", name="ck_inspection_cases_status"),
        sa.CheckConstraint("version >= 1", name="ck_inspection_cases_version"),
        sa.CheckConstraint("snapshot_schema_version = 'inspection-evidence-v1'", name="ck_inspection_cases_snapshot_schema"),
        sa.CheckConstraint("jsonb_typeof(evidence_snapshot) = 'object'", name="ck_inspection_cases_snapshot_shape"),
        sa.CheckConstraint("result IS NULL OR result IN ('NO_ACTION', 'MONITOR', 'MAINTENANCE_RECOMMENDED')", name="ck_inspection_cases_result"),
        sa.CheckConstraint(
            "(status = 'OPEN' AND started_at_utc IS NULL AND completed_at_utc IS NULL "
            "AND cancelled_at_utc IS NULL AND result IS NULL AND result_notes IS NULL) OR "
            "(status = 'IN_PROGRESS' AND started_at_utc IS NOT NULL "
            "AND completed_at_utc IS NULL AND cancelled_at_utc IS NULL "
            "AND result IS NULL AND result_notes IS NULL) OR "
            "(status = 'COMPLETED' AND started_at_utc IS NOT NULL "
            "AND completed_at_utc IS NOT NULL AND cancelled_at_utc IS NULL "
            "AND result IS NOT NULL AND result_notes IS NOT NULL "
            "AND btrim(result_notes) <> '') OR "
            "(status = 'CANCELLED' AND completed_at_utc IS NULL "
            "AND cancelled_at_utc IS NOT NULL AND result IS NULL AND result_notes IS NULL)",
            name="ck_inspection_cases_state",
        ),
        sa.ForeignKeyConstraint(["tractor_id"], ["tractors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inspection_cases_tractor_history", "inspection_cases", ["tractor_id", "created_at_utc", "id"], unique=False)
    op.create_index("uq_inspection_cases_active_tractor", "inspection_cases", ["tractor_id"], unique=True, postgresql_where=sa.text("status IN ('OPEN', 'IN_PROGRESS')"))


def downgrade() -> None:
    op.drop_index("uq_inspection_cases_active_tractor", table_name="inspection_cases")
    op.drop_index("ix_inspection_cases_tractor_history", table_name="inspection_cases")
    op.drop_table("inspection_cases")
    op.drop_index("ix_scored_windows_telemetry_import", table_name="scored_windows")
    op.drop_constraint("fk_scored_windows_telemetry_import", "scored_windows", type_="foreignkey")
    op.drop_column("scored_windows", "telemetry_import_id")
    op.drop_index("ix_telemetry_samples_import_observed", table_name="telemetry_samples")
    op.drop_table("telemetry_samples")
    op.drop_table("telemetry_missions")
    op.drop_index("ix_telemetry_imports_tractor_interval", table_name="telemetry_imports")
    op.drop_table("telemetry_imports")
