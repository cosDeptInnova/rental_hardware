from fastapi import Header, HTTPException, status, Depends
from .security import require_api_key_header, hash_api_key
from .db import get_client_by_api_hash

def get_current_client(x_api_key: str | None = Header(default=None)):
    plain = require_api_key_header(x_api_key)
    row = get_client_by_api_hash(hash_api_key(plain))
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return row

def require_scope(scope: str):
    def checker(client = Depends(get_current_client)):
        scopes = set((client["scopes"] or "").split(","))
        if scope not in scopes and not client["is_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing scope: {scope}",
            )
        return client
    return checker

def require_admin(client = Depends(get_current_client)):
    if not client["is_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin scope required",
        )
    return client
