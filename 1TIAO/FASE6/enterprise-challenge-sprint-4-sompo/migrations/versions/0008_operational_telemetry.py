"""Accept explicitly labelled operational CSV periods without changing frozen replay."""
from alembic import op
import sqlalchemy as sa

revision = "0008_operational_telemetry"
down_revision = "0007_admin_accounts"
branch_labels = None
depends_on = None

OLD = {
    "ck_telemetry_imports_split": "dataset_split IN ('train', 'validation')",
    "ck_telemetry_imports_source_format": "source_format IN ('canonical_csv', 'canonical_csv_gz', 'fendt314_zip')",
    "ck_telemetry_imports_source_member": "(source_format = 'fendt314_zip' AND source_member IS NOT NULL) OR (source_format IN ('canonical_csv', 'canonical_csv_gz') AND source_member IS NULL)",
    "ck_telemetry_imports_epoch": "epoch_utc = TIMESTAMPTZ '2024-04-26 13:22:25.100+00'",
    "ck_telemetry_imports_transform": "transform_version IN ('canonical-pass-through-v1', 'fendt314-original-to-1hz-v1')",
}
NEW = {
    "ck_telemetry_imports_split": "dataset_split IN ('train', 'validation', 'operational')",
    "ck_telemetry_imports_source_format": "source_format IN ('canonical_csv', 'canonical_csv_gz', 'fendt314_zip', 'operational_csv')",
    "ck_telemetry_imports_source_member": "(source_format = 'fendt314_zip' AND source_member IS NOT NULL) OR (source_format IN ('canonical_csv', 'canonical_csv_gz', 'operational_csv') AND source_member IS NULL)",
    "ck_telemetry_imports_epoch": "dataset_split = 'operational' OR epoch_utc = TIMESTAMPTZ '2024-04-26 13:22:25.100+00'",
    "ck_telemetry_imports_transform": "transform_version IN ('canonical-pass-through-v1', 'fendt314-original-to-1hz-v1', 'operational-utc-1hz-v1')",
}
OLD_PROVENANCE = "source_kind = 'observed_dataset_replay' AND dataset_split IN ('train', 'validation') AND btrim(source_reference) <> ''"
NEW_PROVENANCE = "((source_kind = 'observed_dataset_replay' AND dataset_split IN ('train', 'validation')) OR (source_kind IN ('simulated_csv', 'operational_csv') AND dataset_split = 'operational')) AND btrim(source_reference) <> ''"


def upgrade() -> None:
    op.add_column("telemetry_imports", sa.Column("source_kind", sa.String(32), nullable=False, server_default="observed_dataset_replay"))
    op.add_column("telemetry_imports", sa.Column("imported_by_worker_id", sa.String(20), nullable=True))
    for name, condition in NEW.items():
        op.drop_constraint(name, "telemetry_imports", type_="check")
        op.create_check_constraint(name, "telemetry_imports", condition)
    op.create_check_constraint("ck_telemetry_imports_origin", "telemetry_imports",
        "(source_kind = 'observed_dataset_replay' AND dataset_split IN ('train', 'validation') AND source_format <> 'operational_csv' AND transform_version <> 'operational-utc-1hz-v1') OR "
        "(source_kind IN ('simulated_csv', 'operational_csv') AND dataset_split = 'operational' AND source_format = 'operational_csv' AND transform_version = 'operational-utc-1hz-v1')")
    op.drop_constraint("ck_scored_windows_provenance", "scored_windows", type_="check")
    op.create_check_constraint("ck_scored_windows_provenance", "scored_windows", NEW_PROVENANCE)


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM telemetry_imports WHERE dataset_split = 'operational' LIMIT 1")).first():
        raise RuntimeError("cannot discard operational or simulated telemetry imports")
    op.drop_constraint("ck_scored_windows_provenance", "scored_windows", type_="check")
    op.create_check_constraint("ck_scored_windows_provenance", "scored_windows", OLD_PROVENANCE)
    op.drop_constraint("ck_telemetry_imports_origin", "telemetry_imports", type_="check")
    for name, condition in OLD.items():
        op.drop_constraint(name, "telemetry_imports", type_="check")
        op.create_check_constraint(name, "telemetry_imports", condition)
    op.drop_column("telemetry_imports", "imported_by_worker_id")
    op.drop_column("telemetry_imports", "source_kind")
