from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from apps.bastion_control_plane.db.session import get_db
from apps.bastion_control_plane.models.db_models import ApiKey


def require_api_key(x_api_key: str = Header(default=""), db: Session = Depends(get_db)) -> ApiKey:
    key = db.scalar(select(ApiKey).where(ApiKey.key == x_api_key, ApiKey.active.is_(True)))
    if not key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return key
