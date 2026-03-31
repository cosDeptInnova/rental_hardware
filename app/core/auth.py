from __future__ import annotations

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.models import Tenant
from app.services.session_control import session_control


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_api_key(raw: str, hashed: str) -> bool:
    return secrets.compare_digest(hash_api_key(raw), hashed)


def get_current_tenant(
    x_api_key: Annotated[str, Header(alias="X-API-Key")],
    db: Session = Depends(get_db),
) -> Tenant:
    stmt = select(Tenant).where(Tenant.api_key_hash == hash_api_key(x_api_key), Tenant.status == "active")
    tenant = db.execute(stmt).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_api_key")
    if session_control.is_revoked(tenant.id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session_revoked")
    return tenant


def require_admin(
    x_admin_token: Annotated[str, Header(alias="X-Admin-Token")],
) -> None:
    if not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
