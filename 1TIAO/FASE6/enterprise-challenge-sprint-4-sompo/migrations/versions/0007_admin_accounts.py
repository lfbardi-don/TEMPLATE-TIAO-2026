"""Add global administrator accounts and account action history.

Revision ID: 0007_admin_accounts
Revises: 0006_inspection_case_events
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_admin_accounts"
down_revision = "0006_inspection_case_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_constraint("ck_users_fleet_scope", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('ADMIN', 'INSURER', 'INSPECTOR', 'FLEET_MANAGER')",
    )
    op.create_check_constraint(
        "ck_users_fleet_scope",
        "users",
        "(role = 'FLEET_MANAGER' AND fleet_id IS NOT NULL) OR "
        "(role IN ('ADMIN', 'INSURER', 'INSPECTOR') AND fleet_id IS NULL)",
    )
    op.create_table(
        "admin_user_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_worker_id", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_worker_id", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("occurred_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "action IN ('CREATE', 'UPDATE', 'RESET_PASSWORD')",
            name="ck_admin_user_events_action",
        ),
        sa.CheckConstraint(
            "target_worker_id ~ '^[0-9]{1,20}$'",
            name="ck_admin_user_events_target_worker_id",
        ),
        sa.CheckConstraint(
            "actor_worker_id ~ '^[0-9]{1,20}$'",
            name="ck_admin_user_events_actor_worker_id",
        ),
        sa.CheckConstraint("jsonb_typeof(details) = 'object'", name="ck_admin_user_events_details_shape"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_user_events_time", "admin_user_events", ["occurred_at_utc", "id"]
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM admin_user_events LIMIT 1")).first():
        raise RuntimeError("cannot discard admin account event history")
    if connection.execute(sa.text("SELECT 1 FROM users WHERE role = 'ADMIN' LIMIT 1")).first():
        raise RuntimeError("cannot downgrade while ADMIN accounts exist")
    op.drop_index("ix_admin_user_events_time", table_name="admin_user_events")
    op.drop_table("admin_user_events")
    op.drop_constraint("ck_users_fleet_scope", "users", type_="check")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint(
        "ck_users_role",
        "users",
        "role IN ('INSURER', 'INSPECTOR', 'FLEET_MANAGER')",
    )
    op.create_check_constraint(
        "ck_users_fleet_scope",
        "users",
        "(role = 'FLEET_MANAGER' AND fleet_id IS NOT NULL) OR "
        "(role IN ('INSURER', 'INSPECTOR') AND fleet_id IS NULL)",
    )
