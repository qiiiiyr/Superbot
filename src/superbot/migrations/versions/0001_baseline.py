"""baseline: actions, audit_log, llm_usage, settings_kv

Revision ID: 0001
Revises:
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UTC_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "actions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("created_at", UTC_TS, nullable=False),
        sa.Column("decided_at", UTC_TS),
        sa.Column("executed_at", UTC_TS),
        sa.Column("result", sa.JSON),
        sa.Column("error", sa.Text),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("action_id", sa.Integer, sa.ForeignKey("actions.id"), index=True),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("actor", sa.String(50), nullable=False),
        sa.Column("detail", sa.Text),
        sa.Column("at", UTC_TS, nullable=False),
    )
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("at", UTC_TS, nullable=False, index=True),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cost_cents", sa.Integer, nullable=False),
    )
    op.create_table(
        "settings_kv",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )


def downgrade() -> None:
    for t in ("settings_kv", "llm_usage", "audit_log", "actions"):
        op.drop_table(t)
