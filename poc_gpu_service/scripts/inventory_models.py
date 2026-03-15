import json
from pathlib import Path
from shared.config import get_settings
from shared.utils.catalog import CatalogService


def main():
    s = get_settings()
    cat = CatalogService(s.catalog_path, s.model_storage_root)
    items = []
    for m in cat.load():
        p = Path(s.model_storage_root) / m["local_path"]
        items.append({"model_alias": m["model_alias"], "exists": p.exists(), "path": str(p)})
    print(json.dumps({"items": items}, indent=2))


if __name__ == "__main__":
    main()
