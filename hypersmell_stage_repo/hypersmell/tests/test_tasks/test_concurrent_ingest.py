"""Concurrency test for the idempotency fix in store.py.

When Inngest delivers an event twice (at-least-once delivery), the pipeline
should not create duplicate chunks. The delete-before-insert strategy in
store_chunks ensures that re-processing the same resource is safe.
"""
from unittest.mock import MagicMock, patch

from sqlmodel import text

from hypersmell.models import Chunk, Resource


def test_no_duplicate_chunks_on_concurrent_processing(session, workspace):
    """Simulates duplicate processing of the same resource.

    When Inngest delivers an event twice (at-least-once delivery),
    the pipeline should not create duplicate chunks.
    """
    resource = Resource(
        workspace_id=workspace.id,
        integration="supplier_catalog",
        external_id="test_concurrent",
        title="Test Concurrent Resource",
        content="This is a short test document for concurrency testing.",
        status="pending",
    )
    session.add(resource)
    session.commit()
    session.refresh(resource)

    # Mock embed_chunks to avoid loading the real model and numpy dependency
    def fake_embed_chunks(chunks, model_name="all-MiniLM-L6-v2"):
        for chunk in chunks:
            chunk["embedding"] = [0.1] * 384
        return chunks

    with patch("hypersmell.pipeline.orchestrator.embed_chunks", side_effect=fake_embed_chunks):
        from hypersmell.pipeline.orchestrator import process_resource

        # Process the same resource twice (simulating at-least-once delivery)
        process_resource(session, resource)
        process_resource(session, resource)

    from sqlmodel import select
    # Check for duplicates — should have exactly 1 chunk, not 2+
    rows = session.exec(
        select(Chunk).where(Chunk.resource_id == resource.id)
    ).all()

    # With delete-before-insert, the second run replaces the first run's chunks
    assert len(rows) == 1, f"Expected 1 chunk, got {len(rows)} (duplicates!)"
