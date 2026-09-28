"""Local accounts and revocable sessions for the single-machine demo.

Revision ID: 0005_auth_rbac
Revises: 0004_inspection_findings
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0005_auth_rbac"
down_revision = "0004_inspection_findings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("fleet_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('INSURER', 'INSPECTOR', 'FLEET_MANAGER')",
            name="ck_users_role",
        ),
        sa.CheckConstraint("worker_id ~ '^[0-9]{1,20}$'", name="ck_users_worker_id"),
        sa.CheckConstraint(
            "(role = 'FLEET_MANAGER' AND fleet_id IS NOT NULL) OR "
            "(role IN ('INSURER', 'INSPECTOR') AND fleet_id IS NULL)",
            name="ck_users_fleet_scope",
        ),
        sa.ForeignKeyConstraint(["fleet_id"], ["fleets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_id", name="uq_users_worker_id"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_digest"),
    )
    op.create_index(
        "ix_user_sessions_user_expiry", "user_sessions", ["user_id", "expires_at_utc"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_user_expiry", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
