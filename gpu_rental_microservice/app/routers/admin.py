import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import settings
from ..db import (
    add_client_certificate,
    add_client_ip_allowlist,
    create_api_key,
    create_client,
    create_plan,
    deactivate_client,
    deactivate_plan,
    get_client_by_name,
    get_plan,
    insert_config_audit,
    list_client_ip_allowlist,
    list_clients,
    list_plans,
    remove_client_ip_allowlist,
    revoke_all_api_keys_for_client,
    revoke_client_certificate,
    update_client,
    update_plan,
    utcnow_iso,
)
from ..deps import require_admin
from ..models import (
    ApiKeyRotateRequest,
    ApiKeyRotateResponse,
    ClientCertificateEntry,
    ClientCreate,
    ClientIpAllowlistEntry,
    ClientPublic,
    ClientUpdate,
    PlanCreate,
    PlanPublic,
    PlanUpdate,
)
from ..security import generate_api_key, hash_api_key, utcnow

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _to_client_public(row) -> ClientPublic:
    payload = dict(row)
    payload["scopes"] = (payload.get("scopes") or "").split(",") if payload.get("scopes") else []
    payload["is_admin"] = bool(payload["is_admin"])
    payload["is_active"] = bool(payload["is_active"])
    return ClientPublic(**payload)


def _to_plan_public(row) -> PlanPublic:
    payload = dict(row)
    payload["is_active"] = bool(payload["is_active"])
    return PlanPublic(**payload)


def _build_diff(before: dict, after: dict) -> dict:
    diff = {}
    for k, new_v in after.items():
        old_v = before.get(k)
        if old_v != new_v:
            diff[k] = {"before": old_v, "after": new_v}
    return diff


def _create_and_store_api_key(client_name: str, expires_in_days: int | None = None):
    plain = generate_api_key(client_name)
    key_hash, key_salt = hash_api_key(plain)
    now_iso = utcnow_iso()
    key_id = str(uuid.uuid4())
    ttl_days = expires_in_days if expires_in_days is not None else settings.api_key_ttl_days
    expires_at = (utcnow() + timedelta(days=ttl_days)).replace(microsecond=0).isoformat() if ttl_days else None
    create_api_key(client_name=client_name, key_id=key_id, key_hash=key_hash, key_salt=key_salt, created_at=now_iso, expires_at=expires_at)
    return key_id, plain, now_iso, expires_at


@router.get("/clients", response_model=list[ClientPublic])
def admin_clients(_=Depends(require_admin)):
    return [_to_client_public(r) for r in list_clients()]


@router.post("/clients", response_model=ClientPublic, status_code=status.HTTP_201_CREATED)
def admin_create_client(payload: ClientCreate, admin=Depends(require_admin)):
    if get_client_by_name(payload.client_name):
        raise HTTPException(status_code=409, detail="client_name already exists")

    now = utcnow_iso()
    data = payload.model_dump()
    data.pop("api_key")
    data["scopes"] = ",".join(data["scopes"])
    data["is_admin"] = int(data["is_admin"])
    data["is_active"] = 1
    data["created_at"] = now
    data["updated_at"] = now
    create_client(data)

    _create_and_store_api_key(payload.client_name)

    created = get_client_by_name(payload.client_name)
    insert_config_audit(
        actor_client_name=admin["client_name"],
        entity_type="client",
        entity_name=payload.client_name,
        action="create",
        diff={"created": payload.model_dump(exclude={"api_key"})},
    )
    return _to_client_public(created)


@router.post("/clients/{client_name}/api-keys/rotate", response_model=ApiKeyRotateResponse)
def admin_rotate_client_api_key(client_name: str, payload: ApiKeyRotateRequest, admin=Depends(require_admin)):
    current = get_client_by_name(client_name)
    if not current:
        raise HTTPException(status_code=404, detail="Client not found")
    if payload.revoke_previous:
        revoke_all_api_keys_for_client(client_name, utcnow_iso())
    key_id, plain, created_at, expires_at = _create_and_store_api_key(client_name, payload.expires_in_days)
    insert_config_audit(
        actor_client_name=admin["client_name"],
        entity_type="api_key",
        entity_name=client_name,
        action="rotate",
        diff={"key_id": key_id, "expires_at": expires_at, "revoke_previous": payload.revoke_previous},
    )
    return ApiKeyRotateResponse(key_id=key_id, api_key=plain, created_at=created_at, expires_at=expires_at)


@router.post("/clients/{client_name}/ip-allowlist")
def admin_add_ip_allowlist(client_name: str, payload: ClientIpAllowlistEntry, admin=Depends(require_admin)):
    if not get_client_by_name(client_name):
        raise HTTPException(status_code=404, detail="Client not found")
    add_client_ip_allowlist(client_name, payload.ip_cidr, utcnow_iso())
    insert_config_audit(admin["client_name"], "client_ip_allowlist", client_name, "add", {"ip_cidr": payload.ip_cidr})
    return {"client_name": client_name, "ip_allowlist": [r["ip_cidr"] for r in list_client_ip_allowlist(client_name)]}


@router.delete("/clients/{client_name}/ip-allowlist")
def admin_remove_ip_allowlist(client_name: str, payload: ClientIpAllowlistEntry, admin=Depends(require_admin)):
    remove_client_ip_allowlist(client_name, payload.ip_cidr)
    insert_config_audit(admin["client_name"], "client_ip_allowlist", client_name, "remove", {"ip_cidr": payload.ip_cidr})
    return {"client_name": client_name, "ip_allowlist": [r["ip_cidr"] for r in list_client_ip_allowlist(client_name)]}


@router.post("/clients/{client_name}/certificates")
def admin_add_certificate(client_name: str, payload: ClientCertificateEntry, admin=Depends(require_admin)):
    add_client_certificate(client_name, payload.fingerprint, utcnow_iso())
    insert_config_audit(admin["client_name"], "client_certificate", client_name, "add", {"fingerprint": payload.fingerprint})
    return {"status": "ok"}


@router.post("/clients/{client_name}/certificates/revoke")
def admin_revoke_certificate(client_name: str, payload: ClientCertificateEntry, admin=Depends(require_admin)):
    revoke_client_certificate(payload.fingerprint, utcnow_iso())
    insert_config_audit(admin["client_name"], "client_certificate", client_name, "revoke", {"fingerprint": payload.fingerprint})
    return {"status": "ok"}


@router.patch("/clients/{client_name}", response_model=ClientPublic)
def admin_update_client(client_name: str, payload: ClientUpdate, admin=Depends(require_admin)):
    current = get_client_by_name(client_name)
    if not current:
        raise HTTPException(status_code=404, detail="Client not found")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No changes requested")

    if "max_power_watts" in updates or "max_energy_joules_per_job" in updates:
        power = float(updates.get("max_power_watts", current["max_power_watts"]))
        energy = float(updates.get("max_energy_joules_per_job", current["max_energy_joules_per_job"]))
        if energy < power:
            raise HTTPException(status_code=400, detail="max_energy_joules_per_job must be >= max_power_watts")

    if "api_key" in updates:
        updates.pop("api_key")
        _create_and_store_api_key(client_name)
    if "scopes" in updates:
        updates["scopes"] = ",".join(updates["scopes"])
    if "is_admin" in updates:
        updates["is_admin"] = int(updates["is_admin"])
    if "is_active" in updates:
        updates["is_active"] = int(updates["is_active"])

    updates["updated_at"] = utcnow_iso()
    update_client(client_name, updates)
    updated = get_client_by_name(client_name)

    safe_updates = {k: v for k, v in payload.model_dump(exclude_none=True).items() if k != "api_key"}
    insert_config_audit(
        actor_client_name=admin["client_name"],
        entity_type="client",
        entity_name=client_name,
        action="update",
        diff=_build_diff(dict(current), safe_updates),
    )
    return _to_client_public(updated)


@router.post("/clients/{client_name}/deactivate", response_model=ClientPublic)
def admin_deactivate_client(client_name: str, admin=Depends(require_admin)):
    current = get_client_by_name(client_name)
    if not current:
        raise HTTPException(status_code=404, detail="Client not found")
    deactivate_client(client_name)
    updated = get_client_by_name(client_name)
    insert_config_audit(
        actor_client_name=admin["client_name"],
        entity_type="client",
        entity_name=client_name,
        action="deactivate",
        diff={"is_active": {"before": bool(current["is_active"]), "after": False}},
    )
    return _to_client_public(updated)


@router.get("/plans", response_model=list[PlanPublic])
def admin_list_plans(_=Depends(require_admin)):
    return [_to_plan_public(r) for r in list_plans()]


@router.post("/plans", response_model=PlanPublic, status_code=status.HTTP_201_CREATED)
def admin_create_plan(payload: PlanCreate, admin=Depends(require_admin)):
    if get_plan(payload.plan_name):
        raise HTTPException(status_code=409, detail="plan_name already exists")
    plan = payload.model_dump()
    now = utcnow_iso()
    plan["is_active"] = 1
    plan["created_at"] = now
    plan["updated_at"] = now
    create_plan(plan)
    created = get_plan(payload.plan_name)
    insert_config_audit(
        actor_client_name=admin["client_name"],
        entity_type="plan",
        entity_name=payload.plan_name,
        action="create",
        diff={"created": payload.model_dump()},
    )
    return _to_plan_public(created)


@router.patch("/plans/{plan_name}", response_model=PlanPublic)
def admin_update_plan(plan_name: str, payload: PlanUpdate, admin=Depends(require_admin)):
    current = get_plan(plan_name)
    if not current:
        raise HTTPException(status_code=404, detail="Plan not found")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No changes requested")

    if "max_power_watts" in updates or "max_energy_joules" in updates:
        power = float(updates.get("max_power_watts", current["max_power_watts"]))
        energy = float(updates.get("max_energy_joules", current["max_energy_joules"]))
        if energy < power:
            raise HTTPException(status_code=400, detail="max_energy_joules must be >= max_power_watts")

    if "is_active" in updates:
        updates["is_active"] = int(updates["is_active"])
    updates["updated_at"] = utcnow_iso()
    update_plan(plan_name, updates)
    updated = get_plan(plan_name)

    insert_config_audit(
        actor_client_name=admin["client_name"],
        entity_type="plan",
        entity_name=plan_name,
        action="update",
        diff=_build_diff(dict(current), payload.model_dump(exclude_none=True)),
    )
    return _to_plan_public(updated)


@router.post("/plans/{plan_name}/deactivate", response_model=PlanPublic)
def admin_deactivate_plan(plan_name: str, admin=Depends(require_admin)):
    current = get_plan(plan_name)
    if not current:
        raise HTTPException(status_code=404, detail="Plan not found")
    deactivate_plan(plan_name)
    updated = get_plan(plan_name)
    insert_config_audit(
        actor_client_name=admin["client_name"],
        entity_type="plan",
        entity_name=plan_name,
        action="deactivate",
        diff={"is_active": {"before": bool(current["is_active"]), "after": False}},
    )
    return _to_plan_public(updated)
