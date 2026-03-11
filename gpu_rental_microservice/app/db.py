import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

from .config import settings

_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_conn():
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_name TEXT UNIQUE NOT NULL,
                requests_per_minute INTEGER NOT NULL,
                max_concurrent_jobs INTEGER NOT NULL,
                max_job_seconds INTEGER NOT NULL,
                max_input_bytes INTEGER NOT NULL,
                monthly_credit_limit REAL NOT NULL,
                price_per_gpu_second REAL NOT NULL,
                gpu_share REAL NOT NULL,
                max_power_watts REAL NOT NULL DEFAULT 1000,
                max_energy_joules REAL NOT NULL DEFAULT 10000000,
                max_output_tokens INTEGER NOT NULL DEFAULT 100000,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT UNIQUE NOT NULL,
                api_key_hash TEXT,
                scopes TEXT NOT NULL,
                plan_name TEXT NOT NULL,
                requests_per_minute INTEGER NOT NULL,
                max_concurrent_jobs INTEGER NOT NULL,
                max_job_seconds INTEGER NOT NULL,
                max_input_bytes INTEGER NOT NULL,
                monthly_credit_limit REAL NOT NULL,
                price_per_gpu_second REAL NOT NULL,
                gpu_share REAL NOT NULL,
                max_tokens_per_job INTEGER NOT NULL DEFAULT 100000,
                monthly_token_limit INTEGER NOT NULL DEFAULT 1000000,
                max_power_watts REAL NOT NULL DEFAULT 1000,
                max_energy_joules_per_job REAL NOT NULL DEFAULT 10000000,
                is_admin INTEGER NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                client_name TEXT NOT NULL,
                workload_name TEXT NOT NULL,
                status TEXT NOT NULL,
                estimated_seconds INTEGER NOT NULL,
                billed_seconds INTEGER NOT NULL DEFAULT 0,
                gpu_seconds REAL NOT NULL DEFAULT 0,
                peak_vram_mb INTEGER NOT NULL DEFAULT 0,
                input_bytes INTEGER NOT NULL DEFAULT 0,
                output_bytes INTEGER NOT NULL DEFAULT 0,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                idempotency_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                worker_state TEXT NOT NULL DEFAULT 'queued',
                exit_code INTEGER,
                execution_error TEXT,
                avg_gpu_util REAL NOT NULL DEFAULT 0,
                avg_power_watts REAL NOT NULL DEFAULT 0,
                peak_power_watts REAL NOT NULL DEFAULT 0,
                energy_joules REAL NOT NULL DEFAULT 0,
                UNIQUE(client_name, idempotency_key)
            );

            CREATE TABLE IF NOT EXISTS job_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                gpu_util REAL NOT NULL DEFAULT 0,
                memory_used_mb REAL NOT NULL DEFAULT 0,
                power_watts REAL NOT NULL DEFAULT 0,
                energy_joules REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );

            CREATE TABLE IF NOT EXISTS request_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                event_type TEXT NOT NULL DEFAULT 'request',
                event_detail TEXT,
                request_bytes INTEGER NOT NULL DEFAULT 0,
                response_bytes INTEGER NOT NULL DEFAULT 0,
                latency_ms REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                client_name TEXT NOT NULL,
                key_hash TEXT NOT NULL,
                key_salt TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                revoked_at TEXT,
                last_used_at TEXT,
                FOREIGN KEY(client_name) REFERENCES clients(client_name)
            );

            CREATE TABLE IF NOT EXISTS client_certificates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                fingerprint TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(client_name) REFERENCES clients(client_name)
            );

            CREATE TABLE IF NOT EXISTS client_ip_allowlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name TEXT NOT NULL,
                ip_cidr TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(client_name, ip_cidr),
                FOREIGN KEY(client_name) REFERENCES clients(client_name)
            );

            CREATE TABLE IF NOT EXISTS config_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_client_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                action TEXT NOT NULL,
                diff_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            '''
        )
        _ensure_column(conn, "jobs", "worker_state", "TEXT NOT NULL DEFAULT 'queued'")
        _ensure_column(conn, "jobs", "exit_code", "INTEGER")
        _ensure_column(conn, "jobs", "execution_error", "TEXT")
        _ensure_column(conn, "jobs", "avg_gpu_util", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "jobs", "avg_power_watts", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "jobs", "peak_power_watts", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "jobs", "energy_joules", "REAL NOT NULL DEFAULT 0")
        _ensure_column(conn, "jobs", "input_tokens", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "jobs", "output_tokens", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "clients", "max_tokens_per_job", "INTEGER NOT NULL DEFAULT 100000")
        _ensure_column(conn, "clients", "monthly_token_limit", "INTEGER NOT NULL DEFAULT 1000000")
        _ensure_column(conn, "clients", "max_power_watts", "REAL NOT NULL DEFAULT 1000")
        _ensure_column(conn, "clients", "max_energy_joules_per_job", "REAL NOT NULL DEFAULT 10000000")
        _ensure_column(conn, "clients", "updated_at", "TEXT")
        _ensure_column(conn, "request_audit", "event_type", "TEXT NOT NULL DEFAULT 'request'")
        _ensure_column(conn, "request_audit", "event_detail", "TEXT")


def _ensure_column(conn, table_name: str, column_name: str, column_type: str):
    cols = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    if any(c[1] == column_name for c in cols):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def upsert_client(**kwargs):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO clients (
                client_name, scopes, plan_name,
                requests_per_minute, max_concurrent_jobs, max_job_seconds,
                max_input_bytes, monthly_credit_limit, price_per_gpu_second,
                gpu_share, max_tokens_per_job, monthly_token_limit, max_power_watts, max_energy_joules_per_job,
                is_admin, is_active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_name) DO UPDATE SET
                scopes=excluded.scopes,
                plan_name=excluded.plan_name,
                requests_per_minute=excluded.requests_per_minute,
                max_concurrent_jobs=excluded.max_concurrent_jobs,
                max_job_seconds=excluded.max_job_seconds,
                max_input_bytes=excluded.max_input_bytes,
                monthly_credit_limit=excluded.monthly_credit_limit,
                price_per_gpu_second=excluded.price_per_gpu_second,
                gpu_share=excluded.gpu_share,
                max_tokens_per_job=excluded.max_tokens_per_job,
                monthly_token_limit=excluded.monthly_token_limit,
                max_power_watts=excluded.max_power_watts,
                max_energy_joules_per_job=excluded.max_energy_joules_per_job,
                is_admin=excluded.is_admin,
                updated_at=excluded.updated_at
            ''',
            (
                kwargs["client_name"],
                kwargs["scopes"],
                kwargs["plan_name"],
                kwargs["requests_per_minute"],
                kwargs["max_concurrent_jobs"],
                kwargs["max_job_seconds"],
                kwargs["max_input_bytes"],
                kwargs["monthly_credit_limit"],
                kwargs["price_per_gpu_second"],
                kwargs["gpu_share"],
                kwargs.get("max_tokens_per_job", 100_000),
                kwargs.get("monthly_token_limit", 1_000_000),
                kwargs.get("max_power_watts", 1000.0),
                kwargs.get("max_energy_joules_per_job", 10_000_000.0),
                kwargs["is_admin"],
                kwargs.get("is_active", 1),
                kwargs.get("updated_at", utcnow_iso()),
            ),
        )


def create_api_key(client_name: str, key_id: str, key_hash: str, key_salt: str | None, created_at: str, expires_at: str | None):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO api_keys (id, client_name, key_hash, key_salt, created_at, expires_at, revoked_at, last_used_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
            ''',
            (key_id, client_name, key_hash, key_salt, created_at, expires_at),
        )


def revoke_api_key(key_id: str, revoked_at: str):
    with get_conn() as conn:
        conn.execute("UPDATE api_keys SET revoked_at = ? WHERE id = ?", (revoked_at, key_id))


def revoke_all_api_keys_for_client(client_name: str, revoked_at: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE api_keys SET revoked_at = COALESCE(revoked_at, ?) WHERE client_name = ?",
            (revoked_at, client_name),
        )


def touch_api_key_usage(key_id: str, used_at: str):
    with get_conn() as conn:
        conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (used_at, key_id))


def list_active_api_keys_for_client(client_name: str, now_iso: str):
    with get_conn() as conn:
        return conn.execute(
            '''
            SELECT * FROM api_keys
            WHERE client_name = ?
              AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY created_at DESC
            ''',
            (client_name, now_iso),
        ).fetchall()


def find_client_by_api_key(plain_api_key: str, verify_api_key_fn, now_iso: str):
    with get_conn() as conn:
        candidates = conn.execute(
            '''
            SELECT ak.*, c.*
            FROM api_keys ak
            JOIN clients c ON c.client_name = ak.client_name
            WHERE c.is_active = 1
              AND ak.revoked_at IS NULL
              AND (ak.expires_at IS NULL OR ak.expires_at > ?)
            ORDER BY ak.created_at DESC
            ''',
            (now_iso,),
        ).fetchall()
    for row in candidates:
        if verify_api_key_fn(plain_api_key, row["key_hash"], row["key_salt"]):
            return row
    return None


def get_client_by_name(client_name: str):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM clients WHERE client_name = ?",
            (client_name,),
        ).fetchone()


def create_client(client: dict):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO clients (
                client_name, scopes, plan_name, requests_per_minute,
                max_concurrent_jobs, max_job_seconds, max_input_bytes, monthly_credit_limit,
                price_per_gpu_second, gpu_share, max_tokens_per_job, monthly_token_limit,
                max_power_watts, max_energy_joules_per_job, is_admin, is_active, created_at, updated_at
             ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                client["client_name"],
                client["scopes"],
                client["plan_name"],
                client["requests_per_minute"],
                client["max_concurrent_jobs"],
                client["max_job_seconds"],
                client["max_input_bytes"],
                client["monthly_credit_limit"],
                client["price_per_gpu_second"],
                client["gpu_share"],
                client["max_tokens_per_job"],
                client["monthly_token_limit"],
                client["max_power_watts"],
                client["max_energy_joules_per_job"],
                client["is_admin"],
                client.get("is_active", 1),
                client["created_at"],
                client.get("updated_at"),
            ),
        )


def update_client(client_name: str, updates: dict):
    fields = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [client_name]
    with get_conn() as conn:
        conn.execute(f"UPDATE clients SET {fields} WHERE client_name = ?", values)


def deactivate_client(client_name: str):
    update_client(client_name, {"is_active": 0, "updated_at": utcnow_iso()})


def create_plan(plan: dict):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO plans (
                plan_name, requests_per_minute, max_concurrent_jobs, max_job_seconds,
                max_input_bytes, monthly_credit_limit, price_per_gpu_second, gpu_share,
                max_power_watts, max_energy_joules, max_output_tokens, is_active,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                plan["plan_name"],
                plan["requests_per_minute"],
                plan["max_concurrent_jobs"],
                plan["max_job_seconds"],
                plan["max_input_bytes"],
                plan["monthly_credit_limit"],
                plan["price_per_gpu_second"],
                plan["gpu_share"],
                plan["max_power_watts"],
                plan["max_energy_joules"],
                plan["max_output_tokens"],
                plan.get("is_active", 1),
                plan["created_at"],
                plan.get("updated_at"),
            ),
        )


def get_plan(plan_name: str):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM plans WHERE plan_name = ?",
            (plan_name,),
        ).fetchone()


def update_plan(plan_name: str, updates: dict):
    fields = ", ".join(f"{k} = ?" for k in updates.keys())
    values = list(updates.values()) + [plan_name]
    with get_conn() as conn:
        conn.execute(f"UPDATE plans SET {fields} WHERE plan_name = ?", values)


def deactivate_plan(plan_name: str):
    update_plan(plan_name, {"is_active": 0, "updated_at": utcnow_iso()})


def list_plans():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM plans ORDER BY plan_name").fetchall()


def insert_config_audit(actor_client_name: str, entity_type: str, entity_name: str, action: str, diff: dict):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO config_audit (
                actor_client_name, entity_type, entity_name, action, diff_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (actor_client_name, entity_type, entity_name, action, json.dumps(diff, sort_keys=True), utcnow_iso()),
        )


def insert_job(job: dict):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO jobs (
                id, client_name, workload_name, status, estimated_seconds,
                billed_seconds, gpu_seconds, peak_vram_mb, input_bytes,
                output_bytes, input_tokens, output_tokens, idempotency_key, created_at, started_at, finished_at,
                worker_state, exit_code, execution_error, avg_gpu_util, avg_power_watts, peak_power_watts, energy_joules
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                job["id"],
                job["client_name"],
                job["workload_name"],
                job["status"],
                job["estimated_seconds"],
                job["billed_seconds"],
                job["gpu_seconds"],
                job["peak_vram_mb"],
                job["input_bytes"],
                job["output_bytes"],
                job["input_tokens"],
                job["output_tokens"],
                job["idempotency_key"],
                job["created_at"],
                job["started_at"],
                job["finished_at"],
                job["worker_state"],
                job["exit_code"],
                job["execution_error"],
                job["avg_gpu_util"],
                job["avg_power_watts"],
                job["peak_power_watts"],
                job["energy_joules"],
            ),
        )


def insert_job_metric(job_id: str, ts: str, gpu_util: float, memory_used_mb: float, power_watts: float, energy_joules: float):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO job_metrics (job_id, ts, gpu_util, memory_used_mb, power_watts, energy_joules)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (job_id, ts, gpu_util, memory_used_mb, power_watts, energy_joules),
        )


def aggregate_job_metrics(job_id: str):
    with get_conn() as conn:
        return conn.execute(
            '''
            SELECT
                COALESCE(AVG(gpu_util), 0) AS gpu_util,
                COALESCE(MAX(memory_used_mb), 0) AS memory_used_mb,
                COALESCE(AVG(power_watts), 0) AS power_watts,
                COALESCE(MAX(power_watts), 0) AS peak_power_watts,
                COALESCE(MAX(energy_joules), 0) AS energy_joules
            FROM job_metrics
            WHERE job_id = ?
            ''',
            (job_id,),
        ).fetchone()


def get_job(job_id: str):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        return cur.fetchone()


def get_job_by_idempotency(client_name: str, idempotency_key: str):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM jobs WHERE client_name = ? AND idempotency_key = ?",
            (client_name, idempotency_key),
        )
        return cur.fetchone()


def count_running_jobs(client_name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM jobs WHERE client_name = ? AND status IN ('queued','running')",
            (client_name,),
        )
        return int(cur.fetchone()["c"])


def update_job(job_id: str, **kwargs):
    fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
    values = list(kwargs.values()) + [job_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE jobs SET {fields} WHERE id = ?", values)


def insert_audit(**kwargs):
    with get_conn() as conn:
        conn.execute(
            '''
            INSERT INTO request_audit (
                client_name, path, method, status_code, event_type, event_detail,
                request_bytes, response_bytes, latency_ms, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                kwargs["client_name"],
                kwargs["path"],
                kwargs["method"],
                kwargs["status_code"],
                kwargs.get("event_type", "request"),
                kwargs.get("event_detail"),
                kwargs["request_bytes"],
                kwargs["response_bytes"],
                kwargs["latency_ms"],
                kwargs["created_at"],
            ),
        )


def monthly_usage(client_name: str, month_prefix: str):
    with get_conn() as conn:
        jobs = conn.execute(
            '''
            SELECT
                COUNT(*) AS total_requests,
                COALESCE(SUM(input_bytes), 0) AS total_input_bytes,
                COALESCE(SUM(output_bytes), 0) AS total_output_bytes,
                COALESCE(SUM(billed_seconds), 0) AS total_billed_seconds,
                COALESCE(SUM(gpu_seconds), 0) AS total_gpu_seconds,
                COALESCE(MAX(peak_vram_mb), 0) AS total_peak_vram_mb,
                COALESCE(SUM(input_tokens), 0) AS total_input_tokens,
                COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
                COALESCE(SUM(energy_joules), 0) AS total_energy_joules
            FROM jobs
            WHERE client_name = ? AND substr(created_at, 1, 7) = ?
            ''',
            (client_name, month_prefix),
        ).fetchone()

        client = conn.execute(
            "SELECT * FROM clients WHERE client_name = ?",
            (client_name,),
        ).fetchone()
        return jobs, client


def list_clients():
    with get_conn() as conn:
        cur = conn.execute(
            '''
            SELECT client_name, plan_name, requests_per_minute, max_concurrent_jobs,
                   max_job_seconds, max_input_bytes, monthly_credit_limit,
                   price_per_gpu_second, gpu_share, max_tokens_per_job, monthly_token_limit,
                   max_power_watts, max_energy_joules_per_job, is_admin, is_active,
                   created_at, updated_at, scopes
            FROM clients ORDER BY client_name
            '''
        )
        return cur.fetchall()


def utcnow_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat()


def add_client_ip_allowlist(client_name: str, ip_cidr: str, created_at: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO client_ip_allowlist (client_name, ip_cidr, created_at) VALUES (?, ?, ?)",
            (client_name, ip_cidr, created_at),
        )


def remove_client_ip_allowlist(client_name: str, ip_cidr: str):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM client_ip_allowlist WHERE client_name = ? AND ip_cidr = ?",
            (client_name, ip_cidr),
        )


def list_client_ip_allowlist(client_name: str):
    with get_conn() as conn:
        return conn.execute(
            "SELECT ip_cidr FROM client_ip_allowlist WHERE client_name = ? ORDER BY ip_cidr",
            (client_name,),
        ).fetchall()


def add_client_certificate(client_name: str, fingerprint: str, created_at: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO client_certificates (client_name, fingerprint, created_at, revoked_at) VALUES (?, ?, ?, NULL)",
            (client_name, fingerprint, created_at),
        )


def revoke_client_certificate(fingerprint: str, revoked_at: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE client_certificates SET revoked_at = ? WHERE fingerprint = ?",
            (revoked_at, fingerprint),
        )


def get_client_by_cert_fingerprint(fingerprint: str):
    with get_conn() as conn:
        return conn.execute(
            '''
            SELECT c.*
            FROM client_certificates cc
            JOIN clients c ON c.client_name = cc.client_name
            WHERE cc.fingerprint = ?
              AND cc.revoked_at IS NULL
              AND c.is_active = 1
            ''',
            (fingerprint,),
        ).fetchone()


def count_recent_failed_auth(client_name: str, since_iso: str):
    with get_conn() as conn:
        row = conn.execute(
            '''
            SELECT COUNT(*) AS c
            FROM request_audit
            WHERE client_name = ?
              AND event_type = 'auth_failed'
              AND created_at >= ?
            ''',
            (client_name, since_iso),
        ).fetchone()
        return int(row["c"])
