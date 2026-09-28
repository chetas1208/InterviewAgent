import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from hypersmell.auth.api_key import get_workspace_id
from hypersmell.database import get_session
from hypersmell.models import Chunk, Resource

router = APIRouter()


class ResourceResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    integration: str
    external_id: str
    title: str
    status: str
    doc_metadata: dict
    created_at: datetime
    updated_at: datetime


class ResourceDetailResponse(ResourceResponse):
    content: str


@router.get("", response_model=list[ResourceResponse])
def list_resources(
    workspace_id: str = Depends(get_workspace_id),
    session: Session = Depends(get_session),
):
    """List all resources for the authenticated workspace."""
    resources = session.exec(
        select(Resource).where(Resource.workspace_id == uuid.UUID(workspace_id))
    ).all()
    return resources


@router.get("/{resource_id}", response_model=ResourceDetailResponse)
def get_resource(
    resource_id: uuid.UUID,
    workspace_id: str = Depends(get_workspace_id),
    session: Session = Depends(get_session),
):
    """Get a single resource by ID."""
    resource = session.exec(
        select(Resource).where(
            Resource.id == resource_id,
            Resource.workspace_id == uuid.UUID(workspace_id),
        )
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


@router.delete("/{resource_id}", status_code=204)
def delete_resource(
    resource_id: uuid.UUID,
    workspace_id: str = Depends(get_workspace_id),
    session: Session = Depends(get_session),
):
    """Delete a resource and all its chunks."""
    resource = session.exec(
        select(Resource).where(
            Resource.id == resource_id,
            Resource.workspace_id == uuid.UUID(workspace_id),
        )
    ).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Delete associated chunks first
    chunks = session.exec(select(Chunk).where(Chunk.resource_id == resource_id)).all()
    for chunk in chunks:
        session.delete(chunk)

    session.delete(resource)
    session.commit()
