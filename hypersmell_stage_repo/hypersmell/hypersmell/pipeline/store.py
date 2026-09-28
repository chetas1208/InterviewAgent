import uuid

from loguru import logger
from sqlmodel import Session, text

from hypersmell.models import Chunk


def store_chunks(
    session: Session,
    chunks: list[dict],
    resource_id: uuid.UUID,
    workspace_id: uuid.UUID,
    source: str,
) -> list[Chunk]:
    """Store chunks in the database.

    Deletes any existing chunks for this resource first, then inserts
    new ones. This makes the operation idempotent under concurrent or
    retried deliveries (Inngest at-least-once).
    """
    # Delete existing chunks for this resource to ensure idempotency.
    # We use ORM deletion to keep the session state in sync.
    from sqlmodel import select
    existing_chunks = session.exec(
        select(Chunk).where(Chunk.resource_id == resource_id)
    ).all()
    for c in existing_chunks:
        session.delete(c)
    session.flush()

    stored = []
    for chunk in chunks:
        db_chunk = Chunk(
            resource_id=resource_id,
            workspace_id=workspace_id,
            content=chunk["content"],
            embedding=chunk["embedding"],
            chunk_index=chunk["chunk_index"],
            doc_metadata=chunk.get("metadata", {}),
            source=source,
        )
        session.add(db_chunk)
        stored.append(db_chunk)

    session.commit()
    logger.info(f"Stored {len(stored)} chunks for resource {resource_id}")
    return stored

