import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status


SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _derive_api_key(plain: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        plain.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )


def hash_api_key(value: str, salt: bytes | None = None) -> tuple[str, str]:
    salt_bytes = salt or secrets.token_bytes(16)
    digest = _derive_api_key(value, salt_bytes)
    return base64.b64encode(digest).decode("utf-8"), base64.b64encode(salt_bytes).decode("utf-8")


def verify_api_key(plain: str, stored_hash: str, stored_salt: str | None = None) -> bool:
    if not stored_salt:
        return False
    try:
        salt = base64.b64decode(stored_salt.encode("utf-8"))
        expected = base64.b64decode(stored_hash.encode("utf-8"))
    except Exception:
        return False
    candidate = _derive_api_key(plain, salt)
    return hmac.compare_digest(candidate, expected)


def generate_api_key(prefix: str = "rk") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def require_api_key_header(x_api_key: Optional[str]) -> str:
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )
    return x_api_key


def parse_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def verify_jwt_token(token: str, *, secret: str, issuer: str | None = None, audience: str | None = None) -> dict:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT token format") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_sig = _b64url_decode(signature_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT signature")

    header = json.loads(_b64url_decode(header_b64))
    if header.get("alg") != "HS256":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported JWT alg")

    claims = json.loads(_b64url_decode(payload_b64))
    now_ts = int(utcnow().timestamp())
    exp = int(claims.get("exp", 0))
    if exp <= now_ts:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT expired")
    if not claims.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT missing sub")
    if issuer and claims.get("iss") != issuer:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT issuer mismatch")
    if audience and claims.get("aud") != audience:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="JWT audience mismatch")
    return claims
