from pathlib import Path
from shared.config import get_settings
from shared.utils.catalog import CatalogService


def ensure_model(model_alias: str) -> dict:
    s = get_settings()
    catalog = CatalogService(s.catalog_path, s.model_storage_root)
    model = catalog.get_by_alias(model_alias)
    if not model:
        return {"ok": False, "error": "model not found"}
    target = Path(s.model_storage_root) / model["local_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return {"ok": True, "model_alias": model_alias, "status": "already_present", "path": str(target)}
    if model["source_type"] == "local":
        return {"ok": False, "error": f"local source missing: {target}"}
    target.write_text("stub model artifact for PoC", encoding="utf-8")
    return {"ok": True, "model_alias": model_alias, "status": "downloaded_stub", "path": str(target)}
