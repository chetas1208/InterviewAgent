from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session, text

from hypersmell.auth.api_key import get_workspace_id
from hypersmell.database import get_session
from hypersmell.pipeline.embedder import get_model

router = APIRouter()


class SearchResult(BaseModel):
    chunk_id: str
    resource_id: str
    content: str
    metadata: dict
    source: str
    score: float


class SearchResponse(BaseModel):
    results: list[SearchResult]
    query: str


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100),
    scent_family: str | None = Query(None, description="Filter by scent family"),
    workspace_id: str = Depends(get_workspace_id),
    session: Session = Depends(get_session),
):
    """Search across all indexed content using vector similarity."""
    model = get_model()
    query_embedding = model.encode(q).tolist()

    # Call the vector_search SQL function directly
    # No dedup, no full-text component — just raw vector similarity
    results = session.exec(
        text("""
            SELECT chunk_id, resource_id, content, metadata, source, similarity_score
            FROM vector_search(:workspace_id, :embedding, :limit, :scent_family)
        """),
        params={
            "workspace_id": workspace_id,
            "embedding": str(query_embedding),
            "limit": limit,
            "scent_family": scent_family,
        },
    ).all()

    return SearchResponse(
        query=q,
        results=[
            SearchResult(
                chunk_id=str(r.chunk_id),
                resource_id=str(r.resource_id),
                content=r.content,
                metadata=r.metadata,
                source=r.source,
                score=r.similarity_score,
            )
            for r in results
        ],
    )
