from fastapi import Header, HTTPException
from shared.config import get_settings


def require_internal_token(x_internal_token: str = Header(default="")):
    expected = get_settings().internal_agent_token
    if not expected:
        raise HTTPException(status_code=401, detail="Internal token not configured")
    if x_internal_token != expected:
        raise HTTPException(status_code=401, detail="Invalid internal token")
    return True
