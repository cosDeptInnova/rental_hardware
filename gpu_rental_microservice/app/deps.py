from datetime import timedelta
import ipaddress

from fastapi import Depends, Header, HTTPException, Request, status

from .config import settings
from .db import (
    count_recent_failed_auth,
    find_client_by_api_key,
    get_client_by_cert_fingerprint,
    get_client_by_name,
    insert_audit,
    list_client_ip_allowlist,
    touch_api_key_usage,
    utcnow_iso,
)
from .security import parse_bearer_token, require_api_key_header, utcnow, verify_api_key, verify_jwt_token


def _extract_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def _enforce_ip_allowlist(client, request: Request):
    allowed = list_client_ip_allowlist(client["client_name"])
    if not allowed:
        return
    remote_ip = ipaddress.ip_address(_extract_ip(request))
    for cidr in allowed:
        if remote_ip in ipaddress.ip_network(cidr["ip_cidr"], strict=False):
            return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client IP not allowlisted")


def _audit_auth_failure(client_name: str, detail: str):
    now = utcnow()
    insert_audit(
        client_name=client_name,
        path="/auth",
        method="AUTH",
        status_code=401,
        event_type="auth_failed",
        event_detail=detail,
        request_bytes=0,
        response_bytes=0,
        latency_ms=0,
        created_at=utcnow_iso(),
    )
    threshold = settings.failed_auth_alert_threshold
    if threshold <= 0:
        return
    since = (now - timedelta(seconds=settings.failed_auth_alert_window_seconds)).replace(microsecond=0).isoformat()
    failures = count_recent_failed_auth(client_name, since)
    if failures >= threshold:
        insert_audit(
            client_name=client_name,
            path="/security/alerts",
            method="ALERT",
            status_code=429,
            event_type="security_alert",
            event_detail=f"Repeated failed authentication attempts: {failures}",
            request_bytes=0,
            response_bytes=0,
            latency_ms=0,
            created_at=utcnow_iso(),
        )


def get_current_client(
    request: Request,
    x_api_key: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    x_client_cert_fingerprint: str | None = Header(default=None, alias="X-Client-Cert-Fingerprint"),
):
    auth_errors = []

    if settings.enable_api_key_auth and x_api_key:
        row = find_client_by_api_key(require_api_key_header(x_api_key), verify_api_key, utcnow_iso())
        if row:
            touch_api_key_usage(row["id"], utcnow_iso())
            _enforce_ip_allowlist(row, request)
            request.state.authenticated_client_name = row["client_name"]
            request.state.auth_type = "api_key"
            return row
        auth_errors.append("api_key_invalid")

    token = parse_bearer_token(authorization)
    if settings.enable_jwt_auth and token:
        if not settings.jwt_secret:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="JWT auth enabled without JWT_SECRET")
        claims = verify_jwt_token(token, secret=settings.jwt_secret, issuer=settings.jwt_issuer, audience=settings.jwt_audience)
        client_name = claims.get("sub")
        row = get_client_by_name(client_name) if client_name else None
        if row and row["is_active"]:
            _enforce_ip_allowlist(row, request)
            request.state.authenticated_client_name = row["client_name"]
            request.state.auth_type = "jwt"
            return row
        auth_errors.append("jwt_client_invalid")

    if settings.enable_mtls_auth and x_client_cert_fingerprint:
        row = get_client_by_cert_fingerprint(x_client_cert_fingerprint)
        if row:
            _enforce_ip_allowlist(row, request)
            request.state.authenticated_client_name = row["client_name"]
            request.state.auth_type = "mtls"
            return row
        auth_errors.append("mtls_fingerprint_invalid")

    hinted_name = request.headers.get("X-Client-Name", "unknown")
    _audit_auth_failure(hinted_name, ",".join(auth_errors) if auth_errors else "missing_credentials")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing credentials",
    )


def require_scope(scope: str):
    def checker(client=Depends(get_current_client)):
        scopes = set((client["scopes"] or "").split(","))
        if scope not in scopes and not client["is_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing scope: {scope}",
            )
        return client

    return checker


def require_admin(client=Depends(get_current_client)):
    if not client["is_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin scope required",
        )
    return client
