import hashlib
import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from hypersmell.database import get_session
from hypersmell.models import ApiKey, Workspace

router = APIRouter()


class ApiKeyCreate(BaseModel):
    name: str
    workspace_id: uuid.UUID


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    key_prefix: str
    name: str
    created_at: datetime


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Returned once at creation — includes the full key."""
    key: str


@router.post("", response_model=ApiKeyCreatedResponse, status_code=201)
def create_api_key(data: ApiKeyCreate, session: Session = Depends(get_session)):
    """Create an API key for a workspace. Returns the full key once — store it safely."""
    workspace = session.get(Workspace, data.workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    raw_key = "hs_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:8]

    api_key = ApiKey(
        workspace_id=data.workspace_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=data.name,
    )
    session.add(api_key)
    session.commit()
    session.refresh(api_key)

    return ApiKeyCreatedResponse(
        id=api_key.id,
        workspace_id=api_key.workspace_id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        created_at=api_key.created_at,
        key=raw_key,
    )


@router.get("", response_model=list[ApiKeyResponse])
def list_api_keys(workspace_id: uuid.UUID, session: Session = Depends(get_session)):
    """List API keys for a workspace (prefix only, not full key)."""
    workspace = session.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    keys = session.exec(select(ApiKey).where(ApiKey.workspace_id == workspace_id)).all()
    return keys


@router.delete("/{key_id}", status_code=204)
def revoke_api_key(
    key_id: uuid.UUID,
    workspace_id: uuid.UUID,
    session: Session = Depends(get_session),
):
    """Revoke an API key."""
    api_key = session.exec(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.workspace_id == workspace_id)
    ).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    session.delete(api_key)
    session.commit()
