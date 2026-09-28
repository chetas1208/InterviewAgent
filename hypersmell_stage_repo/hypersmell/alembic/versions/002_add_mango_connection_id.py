"""Add mango_connection_id to connections

Revision ID: 002
Revises: 001
Create Date: 2025-08-15 10:30:00.000000
"""
import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("connections", sa.Column("mango_connection_id", sa.String(100), nullable=True))


def downgrade():
    op.drop_column("connections", "mango_connection_id")
