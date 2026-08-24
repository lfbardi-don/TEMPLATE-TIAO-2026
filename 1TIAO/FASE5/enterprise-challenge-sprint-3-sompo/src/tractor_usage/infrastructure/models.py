"""Durable PostgreSQL records owned by the preventive-inspection MVP."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class FleetRecord(Base):
    __tablename__ = "fleets"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    tractors: Mapped[list["TractorRecord"]] = relationship(back_populates="fleet")


class TractorRecord(Base):
    __tablename__ = "tractors"
    __table_args__ = (
        UniqueConstraint("fleet_id", "external_id", name="uq_tractors_fleet_external_id"),
        CheckConstraint("model_name = 'Fendt 314'", name="ck_tractors_model_name"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    fleet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("fleets.id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_name: Mapped[str] = mapped_column(String(32), nullable=False, default="Fendt 314")
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    fleet: Mapped[FleetRecord] = relationship(back_populates="tractors")
    scored_windows: Mapped[list["ScoredWindowRecord"]] = relationship(
        back_populates="tractor"
    )
    telemetry_imports: Mapped[list["TelemetryImportRecord"]] = relationship(
        back_populates="tractor"
    )
    inspection_cases: Mapped[list["InspectionCaseRecord"]] = relationship(
        back_populates="tractor"
    )


class ScoredWindowRecord(Base):
    __tablename__ = "scored_windows"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_scored_windows_idempotency_key"),
        UniqueConstraint(
            "model_version",
            "tractor_id",
            "mission_index",
            "window_index",
            "observed_at_utc",
            name="uq_scored_windows_identity",
        ),
        CheckConstraint(
            "model_version = 'fendt314-hybrid-v2.0.1'",
            name="ck_scored_windows_model_version",
        ),
        CheckConstraint(
            "mission_index >= 0 AND window_index >= 0",
            name="ck_scored_windows_non_negative_identity",
        ),
        CheckConstraint(
            "evidence_role = 'operational_output_only'",
            name="ck_scored_windows_evidence_role",
        ),
        CheckConstraint(
            "jsonb_typeof(model_features) = 'object' "
            "AND jsonb_typeof(physical_durations) = 'object' "
            "AND jsonb_typeof(physical_reasons) = 'array' "
            "AND jsonb_typeof(contextual_reasons) = 'array'",
            name="ck_scored_windows_json_shapes",
        ),
        CheckConstraint(
            "(window_quality = 'partial_coverage' AND sample_count BETWEEN 55 AND 59 "
            "AND span_seconds >= 54.0 AND span_seconds <= 60.000001) OR "
            "(window_quality = 'complete' AND sample_count = 60 "
            "AND span_seconds >= 54.0 AND span_seconds <= 60.000001) OR "
            "(window_quality = 'boundary_jitter' AND sample_count = 61 "
            "AND span_seconds >= 59.0 AND span_seconds <= 60.000001)",
            name="ck_scored_windows_complete_window",
        ),
        CheckConstraint(
            "source_kind = 'observed_dataset_replay' "
            "AND dataset_split IN ('train', 'validation') "
            "AND btrim(source_reference) <> ''",
            name="ck_scored_windows_provenance",
        ),
        Index("ix_scored_windows_tractor_observed_id", "tractor_id", "observed_at_utc", "id"),
        Index("ix_scored_windows_telemetry_import", "telemetry_import_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tractor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tractors.id", ondelete="RESTRICT"), nullable=False
    )
    telemetry_import_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("telemetry_imports.id", ondelete="RESTRICT"),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    mission_index: Mapped[int] = mapped_column(Integer, nullable=False)
    window_index: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    span_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    window_quality: Mapped[str] = mapped_column(String(32), nullable=False)
    model_features: Mapped[dict[str, float | None]] = mapped_column(JSONB, nullable=False)
    physical_durations: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    dataset_split: Mapped[str] = mapped_column(String(16), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence_role: Mapped[str] = mapped_column(String(32), nullable=False)
    operational_regime: Mapped[int] = mapped_column(Integer, nullable=False)
    contextual_rarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    contextual_rarity_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    physical_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    physical_reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    hybrid_alert: Mapped[bool] = mapped_column(Boolean, nullable=False)
    contextual_reasons: Mapped[list[dict[str, float | str]]] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    tractor: Mapped[TractorRecord] = relationship(back_populates="scored_windows")
    telemetry_import: Mapped["TelemetryImportRecord"] = relationship(
        back_populates="scored_windows"
    )


class TelemetryImportRecord(Base):
    __tablename__ = "telemetry_imports"
    __table_args__ = (
        UniqueConstraint(
            "tractor_id", "dataset_split", "source_sha256", "transform_version",
            name="uq_telemetry_imports_source",
        ),
        UniqueConstraint("semantic_sha256", name="uq_telemetry_imports_semantic"),
        CheckConstraint("dataset_split IN ('train', 'validation')", name="ck_telemetry_imports_split"),
        CheckConstraint(
            "source_format IN ('canonical_csv', 'canonical_csv_gz', 'fendt314_zip')",
            name="ck_telemetry_imports_source_format",
        ),
        CheckConstraint(
            "(source_format = 'fendt314_zip' AND source_member IS NOT NULL) OR "
            "(source_format IN ('canonical_csv', 'canonical_csv_gz') AND source_member IS NULL)",
            name="ck_telemetry_imports_source_member",
        ),
        CheckConstraint("source_size_bytes > 0", name="ck_telemetry_imports_source_size"),
        CheckConstraint("sample_count > 0 AND mission_count > 0", name="ck_telemetry_imports_counts"),
        CheckConstraint("schema_version = 'fendt314-telemetry-v1'", name="ck_telemetry_imports_schema"),
        CheckConstraint(
            "epoch_utc = TIMESTAMPTZ '2024-04-26 13:22:25.100+00'",
            name="ck_telemetry_imports_epoch",
        ),
        CheckConstraint(
            "transform_version IN ('canonical-pass-through-v1', 'fendt314-original-to-1hz-v1')",
            name="ck_telemetry_imports_transform",
        ),
        CheckConstraint("ended_at_utc >= started_at_utc", name="ck_telemetry_imports_interval"),
        Index("ix_telemetry_imports_tractor_interval", "tractor_id", "started_at_utc", "ended_at_utc"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tractor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tractors.id", ondelete="RESTRICT"), nullable=False
    )
    dataset_split: Mapped[str] = mapped_column(String(16), nullable=False)
    source_format: Mapped[str] = mapped_column(String(32), nullable=False)
    source_file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_member: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    semantic_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    transform_version: Mapped[str] = mapped_column(String(64), nullable=False)
    epoch_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mission_count: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )

    tractor: Mapped[TractorRecord] = relationship(back_populates="telemetry_imports")
    missions: Mapped[list["TelemetryMissionRecord"]] = relationship(back_populates="telemetry_import")
    scored_windows: Mapped[list[ScoredWindowRecord]] = relationship(back_populates="telemetry_import")


class TelemetryMissionRecord(Base):
    __tablename__ = "telemetry_missions"
    __table_args__ = (
        CheckConstraint("mission_index >= 0 AND origin_position_deciseconds >= 0", name="ck_telemetry_missions_non_negative"),
        CheckConstraint("first_position_deciseconds >= origin_position_deciseconds AND last_position_deciseconds >= first_position_deciseconds", name="ck_telemetry_missions_positions"),
        CheckConstraint("first_source_row >= 0 AND last_source_row >= first_source_row", name="ck_telemetry_missions_source_rows"),
        CheckConstraint("sample_count > 0 AND ended_at_utc >= started_at_utc", name="ck_telemetry_missions_interval"),
    )

    import_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("telemetry_imports.id", ondelete="RESTRICT"), primary_key=True)
    mission_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin_position_deciseconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    first_position_deciseconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_position_deciseconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    first_source_row: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_source_row: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)

    telemetry_import: Mapped[TelemetryImportRecord] = relationship(back_populates="missions")
    samples: Mapped[list["TelemetrySampleRecord"]] = relationship(back_populates="mission")


class TelemetrySampleRecord(Base):
    __tablename__ = "telemetry_samples"
    __table_args__ = (
        ForeignKeyConstraint(
            ["import_id", "mission_index"],
            ["telemetry_missions.import_id", "telemetry_missions.mission_index"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("import_id", "source_row", name="uq_telemetry_samples_source_row"),
        CheckConstraint("mission_index >= 0 AND position_deciseconds >= 0 AND source_row >= 0", name="ck_telemetry_samples_non_negative"),
        Index("ix_telemetry_samples_import_observed", "import_id", "observed_at_utc"),
    )

    import_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    mission_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    position_deciseconds: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_row: Mapped[int] = mapped_column(BigInteger, nullable=False)
    observed_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    engine_rpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_engine_torque_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    engine_load_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    accelerator_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    coolant_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    front_axle_speed_kph: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_over_ground_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    ground_implement_speed_mmps: Mapped[float | None] = mapped_column(Float, nullable=True)
    wheel_vehicle_speed_kph: Mapped[float | None] = mapped_column(Float, nullable=True)
    rear_pto_rpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    rear_hitch_position: Mapped[float | None] = mapped_column(Float, nullable=True)
    rear_hitch_in_work: Mapped[float | None] = mapped_column(Float, nullable=True)
    rear_link_force_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rear_draft_n: Mapped[float | None] = mapped_column(Float, nullable=True)
    ground_machine_speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    machine_selected_speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)
    wheel_machine_speed_mps: Mapped[float | None] = mapped_column(Float, nullable=True)

    mission: Mapped[TelemetryMissionRecord] = relationship(back_populates="samples")


class InspectionCaseRecord(Base):
    __tablename__ = "inspection_cases"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')", name="ck_inspection_cases_status"),
        CheckConstraint("version >= 1", name="ck_inspection_cases_version"),
        CheckConstraint("snapshot_schema_version = 'inspection-evidence-v1'", name="ck_inspection_cases_snapshot_schema"),
        CheckConstraint("jsonb_typeof(evidence_snapshot) = 'object'", name="ck_inspection_cases_snapshot_shape"),
        CheckConstraint("result IS NULL OR result IN ('NO_ACTION', 'MONITOR', 'MAINTENANCE_RECOMMENDED')", name="ck_inspection_cases_result"),
        CheckConstraint(
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
        Index("ix_inspection_cases_tractor_history", "tractor_id", "created_at_utc", "id"),
        Index("uq_inspection_cases_active_tractor", "tractor_id", unique=True, postgresql_where=text("status IN ('OPEN', 'IN_PROGRESS')")),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    tractor_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("tractors.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    assignee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_as_of_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    snapshot_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now_utc)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now_utc)
    started_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tractor: Mapped[TractorRecord] = relationship(back_populates="inspection_cases")
