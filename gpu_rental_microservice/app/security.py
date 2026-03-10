import hashlib
import secrets
from fastapi import Header, HTTPException, status
from typing import Optional

def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def verify_api_key(plain: str, expected_hash: str) -> bool:
    return secrets.compare_digest(hash_api_key(plain), expected_hash)

def require_api_key_header(x_api_key: Optional[str]) -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    return x_api_key
