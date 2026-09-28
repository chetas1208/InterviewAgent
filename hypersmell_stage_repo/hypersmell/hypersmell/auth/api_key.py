import hashlib

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from hypersmell.database import get_session
from hypersmell.models import ApiKey

security = HTTPBearer()


def get_workspace_id(
    credentials: HTTPAuthorizationCredentials = Security(security),
    session: Session = Depends(get_session),
) -> str:
    """Extract and validate API key, return workspace_id."""
    key = credentials.credentials
    key_hash = hashlib.sha256(key.encode()).hexdigest()

    api_key = session.exec(
        select(ApiKey).where(ApiKey.key_hash == key_hash)
    ).first()

    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return str(api_key.workspace_id)
