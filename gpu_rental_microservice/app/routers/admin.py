from fastapi import APIRouter, Depends, HTTPException, status

from ..db import (
    create_client,
    create_plan,
    deactivate_client,
    deactivate_plan,
    get_client_by_name,
    get_plan,
    insert_config_audit,
    list_clients,
    list_plans,
    update_client,
    update_plan,
    utcnow_iso,
)
from ..deps import require_admin
from ..models import (
    ClientCreate,
    ClientPublic,
    ClientUpdate,
    PlanCreate,
    PlanPublic,
    PlanUpdate,
)
from ..security import hash_api_key

router = APIRouter(prefix="/v1/admin", tags=["admin"])


CONFIG_FIELDS = {
    "requests_per_minute",
    "max_concurrent_jobs",
    "max_job_seconds",
    "max_input_bytes",
    "monthly_credit_limit",
    "price_per_gpu_second",
    "gpu_share",
    "max_power_watts",
    "max_energy_joules",
    "max_output_tokens",
}


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


@router.get("/clients", response_model=list[ClientPublic])
def admin_clients(_=Depends(require_admin)):
    return [_to_client_public(r) for r in list_clients()]


@router.post("/clients", response_model=ClientPublic, status_code=status.HTTP_201_CREATED)
def admin_create_client(payload: ClientCreate, admin=Depends(require_admin)):
    if get_client_by_name(payload.client_name):
        raise HTTPException(status_code=409, detail="client_name already exists")

    now = utcnow_iso()
    data = payload.model_dump()
    data["api_key_hash"] = hash_api_key(data.pop("api_key"))
    data["scopes"] = ",".join(data["scopes"])
    data["is_admin"] = int(data["is_admin"])
    data["is_active"] = 1
    data["created_at"] = now
    data["updated_at"] = now
    create_client(data)
    created = get_client_by_name(payload.client_name)
    insert_config_audit(
        actor_client_name=admin["client_name"],
        entity_type="client",
        entity_name=payload.client_name,
        action="create",
        diff={"created": payload.model_dump(exclude={"api_key"})},
    )
    return _to_client_public(created)


@router.patch("/clients/{client_name}", response_model=ClientPublic)
def admin_update_client(client_name: str, payload: ClientUpdate, admin=Depends(require_admin)):
    current = get_client_by_name(client_name)
    if not current:
        raise HTTPException(status_code=404, detail="Client not found")

    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No changes requested")

    if "max_power_watts" in updates or "max_energy_joules" in updates:
        power = float(updates.get("max_power_watts", current["max_power_watts"]))
        energy = float(updates.get("max_energy_joules", current["max_energy_joules"]))
        if energy < power:
            raise HTTPException(status_code=400, detail="max_energy_joules must be >= max_power_watts")

    if "api_key" in updates:
        updates["api_key_hash"] = hash_api_key(updates.pop("api_key"))
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
