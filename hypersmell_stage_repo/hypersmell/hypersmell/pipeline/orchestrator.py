
from loguru import logger
from sqlmodel import Session

from hypersmell.models import Resource
from hypersmell.pipeline.chunker import chunk_document
from hypersmell.pipeline.embedder import embed_chunks
from hypersmell.pipeline.parser import parse_document
from hypersmell.pipeline.store import store_chunks


def process_resource(
    session: Session,
    resource: Resource,
    embedding_model: str = "all-MiniLM-L6-v2",
) -> int:
    """Run the full pipeline for a resource: parse → chunk → embed → store.

    Returns the number of chunks created.
    """
    logger.info(f"Processing resource {resource.id}: {resource.title}")

    resource.status = "processing"
    session.add(resource)
    session.commit()

    try:
        text = parse_document(resource.content, resource.doc_metadata)
        chunks = chunk_document(text)
        
        for chunk in chunks:
            chunk["metadata"] = resource.doc_metadata

        chunks = embed_chunks(chunks, model_name=embedding_model)
        stored = store_chunks(
            session=session,
            chunks=chunks,
            resource_id=resource.id,
            workspace_id=resource.workspace_id,
            source=resource.integration,
        )

        resource.status = "ready"
        session.add(resource)
        session.commit()

        logger.info(f"Resource {resource.id} processed: {len(stored)} chunks")
        return len(stored)

    except Exception as e:
        logger.error(f"Pipeline failed for resource {resource.id}: {e}")
        resource.status = "error"
        session.add(resource)
        session.commit()
        raise
