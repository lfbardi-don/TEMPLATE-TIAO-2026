"""Record who changed an inspection case and when.

Revision ID: 0006_inspection_case_events
Revises: 0005_auth_rbac
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_inspection_case_events"
down_revision = "0005_auth_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inspection_case_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_worker_id", sa.String(length=20), nullable=False),
        sa.Column("actor_role", sa.String(length=16), nullable=False),
        sa.Column("occurred_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prior_status", sa.String(length=16), nullable=True),
        sa.Column("new_status", sa.String(length=16), nullable=False),
        sa.Column("case_version", sa.Integer(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "action IN ('CREATE', 'UPDATE', 'START', 'COMPLETE', 'CANCEL')",
            name="ck_inspection_case_events_action",
        ),
        sa.CheckConstraint("case_version >= 1", name="ck_inspection_case_events_version"),
        sa.CheckConstraint(
            "actor_role IN ('INSURER', 'INSPECTOR', 'FLEET_MANAGER')",
            name="ck_inspection_case_events_actor_role",
        ),
        sa.CheckConstraint(
            "actor_worker_id ~ '^[0-9]{1,20}$'",
            name="ck_inspection_case_events_worker_id",
        ),
        sa.CheckConstraint(
            "prior_status IS NULL OR prior_status IN ('OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
            name="ck_inspection_case_events_prior_status",
        ),
        sa.CheckConstraint(
            "new_status IN ('OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
            name="ck_inspection_case_events_new_status",
        ),
        sa.CheckConstraint("jsonb_typeof(details) = 'object'", name="ck_inspection_case_events_details_shape"),
        sa.ForeignKeyConstraint(["case_id"], ["inspection_cases.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("case_id", "case_version", name="uq_inspection_case_events_version"),
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM inspection_case_events LIMIT 1")).first():
        raise RuntimeError("cannot discard inspection case event history")
    op.drop_table("inspection_case_events")
