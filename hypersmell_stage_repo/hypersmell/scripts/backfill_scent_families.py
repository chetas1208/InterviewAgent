import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from loguru import logger
from sqlmodel import Session, select
from sqlalchemy.orm.attributes import flag_modified

from hypersmell.database import engine
from hypersmell.models import Chunk, Resource
from hypersmell.pipeline.parser import extract_scent_families

def backfill_resources_and_chunks(batch_size: int = 1000):
    logger.info("Starting backfill of scent_families...")
    
    resources_processed = 0
    resources_updated = 0
    chunks_processed = 0
    chunks_updated = 0
    
    with Session(engine) as session:
        # 1. Backfill Resources
        # We process them in batches
        stmt = select(Resource)
        for resource in session.exec(stmt).yield_per(batch_size):
            resources_processed += 1
            
            # Extract families from raw content
            families = extract_scent_families(resource.content)
            
            if not isinstance(resource.doc_metadata, dict):
                resource.doc_metadata = {}
                
            if resource.doc_metadata.get("scent_families") != families:
                resource.doc_metadata["scent_families"] = families
                flag_modified(resource, "doc_metadata")
                resources_updated += 1
                
            if resources_processed % batch_size == 0:
                session.commit()
                logger.info(f"Processed {resources_processed} resources...")
                
        session.commit()
        logger.info(f"Finished resources: {resources_updated}/{resources_processed} updated.")

        # 2. Backfill Chunks
        stmt = select(Chunk)
        for chunk in session.exec(stmt).yield_per(batch_size):
            chunks_processed += 1
            
            # Re-extract based on chunk content, or we could rely on the resource's families.
            # Extracting from chunk content might be more accurate for that specific chunk,
            # or extracting from resource gives the global context. We'll use chunk content
            # since it's faster than joining with resources, and also accurate.
            families = extract_scent_families(chunk.content)
            
            if not isinstance(chunk.doc_metadata, dict):
                chunk.doc_metadata = {}
                
            if chunk.doc_metadata.get("scent_families") != families:
                chunk.doc_metadata["scent_families"] = families
                flag_modified(chunk, "doc_metadata")
                chunks_updated += 1
                
            if chunks_processed % batch_size == 0:
                session.commit()
                logger.info(f"Processed {chunks_processed} chunks...")
                
        session.commit()
        logger.info(f"Finished chunks: {chunks_updated}/{chunks_processed} updated.")
        logger.info("Backfill complete.")

if __name__ == "__main__":
    backfill_resources_and_chunks()
