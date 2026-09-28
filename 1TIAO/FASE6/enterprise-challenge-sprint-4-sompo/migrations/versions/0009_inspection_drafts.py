"""Preserve partial inspection findings and their audit events.

Revision ID: 0009_inspection_drafts
Revises: 0008_operational_telemetry
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_inspection_drafts"
down_revision = "0008_operational_telemetry"
branch_labels = None
depends_on = None


def _findings_rule(status: str) -> str:
    return (
        "(findings IS NULL AND (status <> 'COMPLETED' "
        "OR snapshot_schema_version = 'inspection-evidence-v1')) OR "
        f"(findings IS NOT NULL AND {status} "
        "AND snapshot_schema_version = 'inspection-evidence-v2' "
        "AND jsonb_typeof(findings) = 'array')"
    )


def upgrade() -> None:
    op.drop_constraint("ck_inspection_cases_findings", "inspection_cases", type_="check")
    op.create_check_constraint(
        "ck_inspection_cases_findings", "inspection_cases",
        _findings_rule("status IN ('IN_PROGRESS', 'COMPLETED', 'CANCELLED')"),
    )
    op.drop_constraint("ck_inspection_case_events_action", "inspection_case_events", type_="check")
    op.create_check_constraint(
        "ck_inspection_case_events_action", "inspection_case_events",
        "action IN ('CREATE', 'UPDATE', 'START', 'SAVE_DRAFT', 'COMPLETE', 'CANCEL')",
    )


def downgrade() -> None:
    has_drafts = op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM inspection_cases "
        "WHERE findings IS NOT NULL AND status <> 'COMPLETED') "
        "OR EXISTS (SELECT 1 FROM inspection_case_events WHERE action = 'SAVE_DRAFT')"
    ))
    if has_drafts:
        raise RuntimeError("cannot downgrade: saved inspection findings or draft events exist")
    op.drop_constraint("ck_inspection_cases_findings", "inspection_cases", type_="check")
    op.create_check_constraint(
        "ck_inspection_cases_findings", "inspection_cases", _findings_rule("status = 'COMPLETED'"),
    )
    op.drop_constraint("ck_inspection_case_events_action", "inspection_case_events", type_="check")
    op.create_check_constraint(
        "ck_inspection_case_events_action", "inspection_case_events",
        "action IN ('CREATE', 'UPDATE', 'START', 'COMPLETE', 'CANCEL')",
    )
