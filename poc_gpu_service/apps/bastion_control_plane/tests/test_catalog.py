from shared.config import get_settings
from shared.utils.catalog import CatalogService


def test_catalog_lookup():
    s = get_settings()
    c = CatalogService(s.catalog_path, s.model_storage_root)
    model = c.get_by_alias("llama3-8b-instruct")
    assert model
    assert model["engine"] == "llama_cpp"
