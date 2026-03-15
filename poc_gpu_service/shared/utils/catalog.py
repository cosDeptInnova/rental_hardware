import json
from pathlib import Path
from typing import Any


class CatalogService:
    def __init__(self, catalog_path: str, model_storage_root: str):
        self.catalog_path = Path(catalog_path)
        self.model_storage_root = Path(model_storage_root)

    def load(self) -> list[dict[str, Any]]:
        return json.loads(self.catalog_path.read_text(encoding="utf-8"))

    def list_enabled_for_tenant(self, tenant_id: str) -> list[dict[str, Any]]:
        return [m for m in self.load() if m.get("enabled") and tenant_id in m.get("allowed_tenants", [])]

    def get_by_alias(self, model_alias: str) -> dict[str, Any] | None:
        return next((m for m in self.load() if m.get("model_alias") == model_alias), None)

    def validate_deployable(self, model_alias: str, tenant_id: str) -> tuple[bool, str]:
        model = self.get_by_alias(model_alias)
        if not model:
            return False, "Model alias not found"
        if not model.get("enabled"):
            return False, "Model disabled"
        if tenant_id not in model.get("allowed_tenants", []):
            return False, "Tenant not allowed"
        return True, "ok"
