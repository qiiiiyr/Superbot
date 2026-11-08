"""products found by research

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cj_pid", sa.String(100), nullable=False, unique=True),
        sa.Column("vid", sa.String(100)),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("image_url", sa.Text),
        sa.Column("keyword", sa.String(200)),
        sa.Column("cost_cents", sa.Integer),
        sa.Column("ship_cents", sa.Integer),
        sa.Column("ship_days", sa.Integer),
        sa.Column("ship_method", sa.String(200)),
        sa.Column("sell_cents", sa.Integer),
        sa.Column("profit_cents", sa.Integer),
        sa.Column("score", sa.Integer),
        sa.Column("reason", sa.Text),
        # skipped | proposed | shortlisted | rejected
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("action_id", sa.Integer, sa.ForeignKey("actions.id")),
        sa.Column("found_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("products")
