"""Migration script to identify and re-index documents that were truncated.

Prior to the chunking fix, documents larger than MAX_CHUNK_SIZE were truncated
to a single chunk and the remaining content was lost. This script finds all
such resources by re-parsing their content and checking if the result exceeds
MAX_CHUNK_SIZE. If so, it deletes the existing chunks for that resource and
re-processes the resource.
"""

from loguru import logger
from sqlmodel import Session, select

from hypersmell.database import engine
from hypersmell.models import Chunk, Resource
from hypersmell.pipeline.chunker import MAX_CHUNK_SIZE
from hypersmell.pipeline.orchestrator import process_resource
from hypersmell.pipeline.parser import parse_document


def migrate():
    logger.info("Starting migration to identify and re-index truncated documents.")
    reindexed_count = 0

    with Session(engine) as session:
        # Get all resources
        resources = session.exec(select(Resource)).all()

        for resource in resources:
            if not resource.content:
                continue

            # Parse the document to get the text that was sent to the chunker
            parsed_text = parse_document(resource.content, resource.doc_metadata)

            # If the parsed text is larger than MAX_CHUNK_SIZE, it was likely truncated
            # because the old chunker would only create one chunk.
            # We also check if it only has 1 chunk in the database to be certain it was truncated.
            if len(parsed_text) > MAX_CHUNK_SIZE:
                chunks = session.exec(select(Chunk).where(Chunk.resource_id == resource.id)).all()

                # If it has only 1 chunk, it was definitely truncated by the bug.
                if len(chunks) == 1:
                    logger.info(f"Resource {resource.id} ({resource.title}) was truncated. Re-indexing...")

                    # Delete old chunks
                    for chunk in chunks:
                        session.delete(chunk)
                    session.commit()

                    # Re-process the resource to create new chunks
                    process_resource(session, resource)
                    reindexed_count += 1

    logger.info(f"Migration complete. Re-indexed {reindexed_count} truncated resources.")

if __name__ == "__main__":
    migrate()
