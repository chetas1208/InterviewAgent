"""add scent family search

Revision ID: 002
Revises: 001
Create Date: 2026-05-11

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the existing function
    op.execute("DROP FUNCTION IF EXISTS vector_search")

    # Create the updated vector_search function
    op.execute("""
CREATE OR REPLACE FUNCTION vector_search(
    p_workspace_id UUID,
    p_query_embedding vector(384),
    p_limit INT DEFAULT 10,
    p_scent_family VARCHAR DEFAULT NULL
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
      AND (p_scent_family IS NULL OR c.metadata->'scent_families' @> to_jsonb(p_scent_family::text))
    ORDER BY c.embedding <=> p_query_embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;
""")


def downgrade() -> None:
    # Drop the updated function
    op.execute("DROP FUNCTION IF EXISTS vector_search")

    # Recreate the original vector_search function
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
