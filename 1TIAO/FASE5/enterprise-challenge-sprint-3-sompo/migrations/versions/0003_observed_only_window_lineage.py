"""Require immutable observed-import lineage for every scored window.

Revision ID: 0003_observed_lineage
Revises: 0002_telemetry_inspections
Create Date: 2026-08-23
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_observed_lineage"
down_revision = "0002_telemetry_inspections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Reject scored history instead of pretending it was independently verified."""

    op.execute("LOCK TABLE scored_windows IN ACCESS EXCLUSIVE MODE")
    existing = op.get_bind().scalar(sa.text("SELECT count(*) FROM scored_windows"))
    if existing:
        raise RuntimeError(
            "cannot enforce observed-only window lineage: "
            f"scored_windows contains {existing} unverified row(s); "
            "do not delete or rewrite them, recreate the database and replay an "
            "observed telemetry import"
        )

    op.drop_constraint("ck_scored_windows_provenance", "scored_windows", type_="check")
    op.alter_column("scored_windows", "telemetry_import_id", nullable=False)
    op.alter_column("scored_windows", "dataset_split", nullable=False)
    op.create_check_constraint(
        "ck_scored_windows_provenance",
        "scored_windows",
        "source_kind = 'observed_dataset_replay' "
        "AND dataset_split IN ('train', 'validation') "
        "AND btrim(source_reference) <> ''",
    )


def downgrade() -> None:
    op.drop_constraint("ck_scored_windows_provenance", "scored_windows", type_="check")
    op.alter_column("scored_windows", "dataset_split", nullable=True)
    op.alter_column("scored_windows", "telemetry_import_id", nullable=True)
    op.create_check_constraint(
        "ck_scored_windows_provenance",
        "scored_windows",
        "source_kind IN ('observed_dataset_replay', 'synthetic_demo', 'live_observed') "
        "AND ((source_kind = 'observed_dataset_replay' AND dataset_split IN ('train', 'validation')) "
        "OR (source_kind IN ('synthetic_demo', 'live_observed') AND dataset_split IS NULL))",
    )
