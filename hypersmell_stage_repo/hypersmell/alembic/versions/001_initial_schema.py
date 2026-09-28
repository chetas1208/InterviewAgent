"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-31

"""

import sqlalchemy as sa
import sqlmodel
from pgvector.sqlalchemy import Vector

from alembic import op

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sqlmodel.AutoString(length=255), nullable=False),
        sa.Column("slug", sqlmodel.AutoString(length=100), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("key_hash", sqlmodel.AutoString(length=64), nullable=False),
        sa.Column("key_prefix", sqlmodel.AutoString(length=8), nullable=False),
        sa.Column("name", sqlmodel.AutoString(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "connections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("integration", sqlmodel.AutoString(length=50), nullable=False),
        sa.Column("status", sqlmodel.AutoString(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "resources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("integration", sqlmodel.AutoString(length=50), nullable=False),
        sa.Column("external_id", sqlmodel.AutoString(length=255), nullable=False),
        sa.Column("title", sqlmodel.AutoString(length=500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("status", sqlmodel.AutoString(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "integration", "external_id"),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("resource_id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(384), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("source", sqlmodel.AutoString(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["resource_id"], ["resources.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create vector_search function for cosine similarity search
    op.execute("""
CREATE OR REPLACE FUNCTION vector_search(
    p_workspace_id UUID,
    p_query_embedding vector(384),
    p_limit INT DEFAULT 10
)
RETURNS TABLE (
    chunk_id UUID,
    resource_id UUID,
    content TEXT,
    metadata JSONB,
    source VARCHAR(50),
    similarity_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.resource_id,
        c.content,
        c.metadata,
        c.source,
        1 - (c.embedding <=> p_query_embedding) AS similarity_score
    FROM chunks c
    WHERE c.workspace_id = p_workspace_id
    ORDER BY c.embedding <=> p_query_embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;
""")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS vector_search")
    op.drop_table("chunks")
    op.drop_table("resources")
    op.drop_table("connections")
    op.drop_table("api_keys")
    op.drop_table("workspaces")
    op.execute("DROP EXTENSION IF EXISTS vector")
