import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from hypersmell.database import get_session
from hypersmell.models import Workspace

router = APIRouter()


class WorkspaceCreate(BaseModel):
    name: str
    slug: str


class WorkspaceUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    settings: dict
    created_at: datetime
    updated_at: datetime


@router.post("", response_model=WorkspaceResponse, status_code=201)
def create_workspace(data: WorkspaceCreate, session: Session = Depends(get_session)):
    """Create a new workspace."""
    existing = session.exec(select(Workspace).where(Workspace.slug == data.slug)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Slug already taken")

    workspace = Workspace(name=data.name, slug=data.slug)
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace


@router.get("", response_model=list[WorkspaceResponse])
def list_workspaces(session: Session = Depends(get_session)):
    """List all workspaces."""
    workspaces = session.exec(select(Workspace)).all()
    return workspaces


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(workspace_id: uuid.UUID, session: Session = Depends(get_session)):
    """Get a single workspace by ID."""
    workspace = session.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
def update_workspace(
    workspace_id: uuid.UUID,
    data: WorkspaceUpdate,
    session: Session = Depends(get_session),
):
    """Update a workspace."""
    workspace = session.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if data.name is not None:
        workspace.name = data.name
    if data.slug is not None:
        existing = session.exec(
            select(Workspace).where(Workspace.slug == data.slug, Workspace.id != workspace_id)
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="Slug already taken")
        workspace.slug = data.slug

    workspace.updated_at = datetime.utcnow()
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    return workspace


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: uuid.UUID, session: Session = Depends(get_session)):
    """Delete a workspace."""
    workspace = session.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    session.delete(workspace)
    session.commit()
