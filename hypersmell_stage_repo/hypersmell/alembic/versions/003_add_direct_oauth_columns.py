"""Add direct OAuth columns to connections

Revision ID: 003
Revises: 002
Create Date: 2025-09-20 14:00:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("connections", sa.Column("access_token", sa.Text, nullable=True))
    op.add_column("connections", sa.Column("refresh_token", sa.Text, nullable=True))


def downgrade():
    op.drop_column("connections", "refresh_token")
    op.drop_column("connections", "access_token")
