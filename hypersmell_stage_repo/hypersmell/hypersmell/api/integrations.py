import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from hypersmell.auth.api_key import get_workspace_id
from hypersmell.database import get_session
from hypersmell.models import Connection

router = APIRouter()

# Known integrations in the system
AVAILABLE_INTEGRATIONS = ["supplier_catalog", "tasting_notes"]


class IntegrationStatus(BaseModel):
    integration: str
    connected: bool
    status: str | None = None
    connected_at: datetime | None = None


class ConnectionResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    integration: str
    status: str
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[IntegrationStatus])
def list_integrations(
    workspace_id: str = Depends(get_workspace_id),
    session: Session = Depends(get_session),
):
    """List available integrations and their connection status for the workspace."""
    connections = session.exec(
        select(Connection).where(Connection.workspace_id == uuid.UUID(workspace_id))
    ).all()
    conn_map = {c.integration: c for c in connections}

    return [
        IntegrationStatus(
            integration=name,
            connected=name in conn_map,
            status=conn_map[name].status if name in conn_map else None,
            connected_at=conn_map[name].created_at if name in conn_map else None,
        )
        for name in AVAILABLE_INTEGRATIONS
    ]


@router.post("/{integration}/connect", response_model=ConnectionResponse, status_code=201)
def connect_integration(
    integration: str,
    workspace_id: str = Depends(get_workspace_id),
    session: Session = Depends(get_session),
):
    """Create a connection for an integration."""
    if integration not in AVAILABLE_INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Unknown integration: {integration}")

    existing = session.exec(
        select(Connection).where(
            Connection.workspace_id == uuid.UUID(workspace_id),
            Connection.integration == integration,
        )
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Integration already connected")

    connection = Connection(
        workspace_id=uuid.UUID(workspace_id),
        integration=integration,
        status="active",
    )
    session.add(connection)
    session.commit()
    session.refresh(connection)
    return connection


@router.post("/{integration}/sync")
def sync_integration(
    integration: str,
    workspace_id: str = Depends(get_workspace_id),
    session: Session = Depends(get_session),
):
    """Trigger a sync for an integration. (Inngest not yet wired up.)"""
    if integration not in AVAILABLE_INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Unknown integration: {integration}")

    connection = session.exec(
        select(Connection).where(
            Connection.workspace_id == uuid.UUID(workspace_id),
            Connection.integration == integration,
        )
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Integration not connected")

    # TODO: enqueue Inngest sync event once background tasks are set up
    return {"message": f"Sync queued for {integration}", "status": "pending"}


@router.delete("/{integration}/disconnect", status_code=204)
def disconnect_integration(
    integration: str,
    workspace_id: str = Depends(get_workspace_id),
    session: Session = Depends(get_session),
):
    """Remove a connection for an integration."""
    if integration not in AVAILABLE_INTEGRATIONS:
        raise HTTPException(status_code=404, detail=f"Unknown integration: {integration}")

    connection = session.exec(
        select(Connection).where(
            Connection.workspace_id == uuid.UUID(workspace_id),
            Connection.integration == integration,
        )
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Integration not connected")

    session.delete(connection)
    session.commit()
