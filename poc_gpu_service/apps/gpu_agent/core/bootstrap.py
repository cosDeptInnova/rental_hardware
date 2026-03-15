from sqlalchemy import text

from apps.gpu_agent.db.session import engine, SessionLocal
from apps.gpu_agent.models.db_models import Base


def _table_columns(db, table_name: str) -> set[str]:
    rows = db.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    return {str(r[1]) for r in rows}


def _add_column_if_missing(db, table_name: str, column_name: str, ddl_type: str) -> None:
    if column_name not in _table_columns(db, table_name):
        db.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type}"))


def _apply_sqlite_hardening_migrations(db) -> None:
    _add_column_if_missing(db, "backend_instances", "started_at", "DATETIME")
    _add_column_if_missing(db, "backend_instances", "stopped_at", "DATETIME")
    _add_column_if_missing(db, "backend_instances", "last_healthcheck_at", "DATETIME")
    _add_column_if_missing(db, "backend_instances", "extra_json", "TEXT")
    _add_column_if_missing(db, "backend_instances", "drainable", "BOOLEAN DEFAULT 1")
    _add_column_if_missing(db, "backend_instances", "critical", "BOOLEAN DEFAULT 0")
    _add_column_if_missing(db, "backend_instances", "service_tier", "VARCHAR(50) DEFAULT 'standard'")
    _add_column_if_missing(db, "backend_instances", "preferred_gpu", "VARCHAR(50)")
    _add_column_if_missing(db, "backend_instances", "restore_priority", "INTEGER DEFAULT 100")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _apply_sqlite_hardening_migrations(db)
        db.commit()
    finally:
        db.close()
