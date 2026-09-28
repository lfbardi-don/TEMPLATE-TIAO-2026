"""Accept agenda-bearing v2 evidence snapshots and per-item inspection findings.

Existing v1 cases stay valid and immutable; they simply have no agenda and
therefore never carry findings.

Revision ID: 0004_inspection_findings
Revises: 0003_observed_lineage
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0004_inspection_findings"
down_revision = "0003_observed_lineage"
branch_labels = None
depends_on = None

FINDINGS_RULE = (
    "(findings IS NULL AND (status <> 'COMPLETED' "
    "OR snapshot_schema_version = 'inspection-evidence-v1')) OR "
    "(findings IS NOT NULL AND status = 'COMPLETED' "
    "AND snapshot_schema_version = 'inspection-evidence-v2' "
    "AND jsonb_typeof(findings) = 'array')"
)


def upgrade() -> None:
    op.drop_constraint("ck_inspection_cases_snapshot_schema", "inspection_cases", type_="check")
    op.create_check_constraint(
        "ck_inspection_cases_snapshot_schema",
        "inspection_cases",
        "snapshot_schema_version IN ('inspection-evidence-v1', 'inspection-evidence-v2')",
    )
    op.add_column("inspection_cases", sa.Column("findings", JSONB, nullable=True))
    op.create_check_constraint("ck_inspection_cases_findings", "inspection_cases", FINDINGS_RULE)


def downgrade() -> None:
    existing = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM inspection_cases "
            "WHERE snapshot_schema_version <> 'inspection-evidence-v1'"
        )
    )
    if existing:
        raise RuntimeError(
            f"cannot downgrade: {existing} inspection case(s) use the v2 evidence snapshot"
        )
    op.drop_constraint("ck_inspection_cases_findings", "inspection_cases", type_="check")
    op.drop_column("inspection_cases", "findings")
    op.drop_constraint("ck_inspection_cases_snapshot_schema", "inspection_cases", type_="check")
    op.create_check_constraint(
        "ck_inspection_cases_snapshot_schema",
        "inspection_cases",
        "snapshot_schema_version = 'inspection-evidence-v1'",
    )
